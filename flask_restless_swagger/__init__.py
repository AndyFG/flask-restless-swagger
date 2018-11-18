import json
from uuid import uuid4

import yaml
from urllib import parse as urlparse
from flask import jsonify, request, Blueprint
from flask_restless import APIManager
from sqlalchemy.orm.attributes import InstrumentedAttribute
from flask_restless.helpers import *

sqlalchemy_swagger_type = {
    'INTEGER': {'type': 'integer', 'format': 'int64'},
    'SMALLINT': {'type': 'int32', 'format': 'int32'},
    'NUMERIC': {'type': 'number', 'format': 'int64'},
    'DECIMAL': {'type': 'number', 'format': 'int64'},
    'VARCHAR': {'type': 'string', 'example': 'lorem ipsum...'},
    'TEXT': {'type': 'string', 'example': 'lorem ipsum...'},
    'DATE': {'type': 'date', 'example': '03/11/1988'},
    'TIME': {'type': 'date', 'example': '03/11/1988'},
    'BOOLEAN': {'type': 'boolean', 'example': 'true'},
    'BLOB': {'type': 'binary', 'example': 'Binary data'},
    'BYTEA': {'type': 'binary', 'example': 'Binary data'},
    'BINARY': {'type': 'binary', 'example': 'Binary data'},
    'VARBINARY': {'type': 'binary', 'example': 'Binary data'},
    'FLOAT': {'type': 'float', 'example': '3.14'},
    'REAL': {'type': 'float', 'example': '3.14'},
    'DATETIME': {'type': 'date', 'example': '03/11/1988'},
    'BIGINT': {'type': 'int64', 'format': 'int64'},
    'ENUM': {'type': 'string', 'example': 'Enum content type'},
    'INTERVAL': {'type': 'date', 'example': '03/11/1988'}
}


def get_columns(model):
    """
    Returns a dictionary-like object containing all the columns of the specified `model` class.
    This includes `hybrid attributes`: http://docs.sqlalchemy.org/en/latest/orm/extensions/hybrid.html
    """
    columns = {}
    for superclass in model.__mro__:
        for name, column in superclass.__dict__.items():
            if isinstance(column, InstrumentedAttribute):
                columns[str(name).lower()] = column
    return columns


class SwagAPIManager(object):
    swagger = {
        'swagger': '2.0',
        'info': {},
        'schemes': ['http', 'https'],
        'basePath': '/api',
        'consumes': ['application/json'],
        'produces': ['application/json'],
        'paths': {},
        'definitions': {}
    }

    def __init__(self, app=None, **kwargs):
        self.app = None
        self.manager = None

        if 'swagger' in kwargs:
            self.swagger.update(kwargs.pop('swagger'))

        if app is not None:
            self.init_app(app, **kwargs)

    def add_path(self, model, **kwargs):
        name = model.__tablename__
        schema = model.__name__
        path = kwargs.get('url_prefix', "") + '/' + name
        id_path = "{0}/{{{1}-id}}".format(path, schema.lower())
        model_description = model.__doc__ if model.__doc__ else ''

        self.swagger['paths'][path] = {}

        for method in [m.lower() for m in ['GET', 'POST', 'DELETE', 'PATCH']]:
            if name.capitalize() in self.swagger['definitions']:
                if method == 'get':
                    self.swagger['paths'][path][method] = {
                        'tags': [name.capitalize()],
                        'summary': 'List of %ss' % name,
                        'description': model_description,
                        'parameters': [
                            {'name': 'q', 'in': 'query', 'description': 'Resource params', 'type': 'string'}],
                        'responses': {
                            200: {
                                'description': 'List of %ss' % name,
                                'schema': {
                                    'title': name,
                                    'type': 'array',
                                    'items': {'$ref': '#/definitions/' + name.capitalize()}
                                }
                            }
                        }
                    }

                    if id_path not in self.swagger['paths']:
                        self.swagger['paths'][id_path] = {}

                    self.swagger['paths'][id_path][method] = {
                        'tags': [name.capitalize()],
                        'summary': 'List one ' + name,
                        'description': model_description,
                        'parameters': [{
                            'name': schema.lower() + '_id',
                            'in': 'path',
                            'description': 'ID of ' + schema,
                            'required': True,
                            'type': 'integer',
                            'example': uuid4()
                        }],
                        'responses': {
                            200: {
                                'description': 'Success ' + name,
                                'schema': {
                                    'title': name,
                                    '$ref': '#/definitions/' + name.capitalize()
                                }
                            }
                        }
                    }

                elif method == 'delete':
                    if id_path not in self.swagger['paths']:
                        self.swagger['paths'][id_path] = {}

                    self.swagger['paths']["{0}/{{{1}-id}}".format(path, schema.lower())][method] = {
                        'tags': [name.capitalize()],
                        'summary': 'Delete ' + name,
                        'description': model_description,
                        'parameters': [{
                            'name': schema + '_id',
                            'in': 'path',
                            'description': 'ID of ' + schema,
                            'required': True,
                            'type': 'integer'
                        }],
                        'responses': {
                            200: {
                                'description': 'Success'
                            }
                        }
                    }

                else:
                    response = {200: {'description': 'Success'}}
                    if method == 'post':
                        response.get(200).update(
                            {'schema': {'title': name, '$ref': '#/definitions/' + name.capitalize()}}
                        )

                    self.swagger['paths'][path][method] = {
                        'tags': [name.capitalize()],
                        'summary': '%s %s' % ('Create' if method == 'post' else 'Update', name),
                        'description': model_description,
                        'parameters': [{
                            'name': name.lower(),
                            'in': 'body',
                            'description': schema,
                            'schema': {'$ref': "#/definitions/" + schema}
                        }],
                        'responses': response
                    }

    def add_defn(self, model, **kwargs):
        name = model.__name__
        self.swagger['definitions'][name] = {'type': 'object', 'properties': {}}
        columns = get_columns(model).keys()

        for column_name, column in get_columns(model).items():
            column_defn = None

            if column_name not in kwargs.get('exclude_columns', []):
                try:
                    column_type = str(column.type) if '(' not in str(column.type) else str(column.type).split('(')[0]
                    column_defn = sqlalchemy_swagger_type[column_type]
                except AttributeError:
                    schema = get_related_model(model, column_name)

                    if schema.__name__ in self.swagger['definitions']:
                        if column_name + '_id' in columns:
                            column_defn = {'schema': {'type': 'uuid', '$ref': schema.__name__}}
                        else:
                            column_defn = {'schema': {'type': 'array', 'items': {'$ref': schema.__name__}}}

            if column_defn:
                self.swagger['definitions'][name]['properties'][column_name] = column_defn

    def init_app(self, app, **kwargs):
        self.app = app
        self.manager = APIManager(self.app, **kwargs)

        swagger = Blueprint('swagger', __name__, static_folder='static')

        @swagger.route('/api/api-docs.json')
        def swagger_json():
            self.swagger['host'] = urlparse.urlparse(request.url_root).netloc
            return jsonify(self.swagger)

        app.register_blueprint(swagger)

    def create_api(self, model, **kwargs):
        self.manager.create_api(model, **kwargs)
        self.add_defn(model, **kwargs)
        self.add_path(model, **kwargs)
