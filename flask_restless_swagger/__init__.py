import json
import yaml
from urllib import parse as urlparse
from flask import jsonify, request, Blueprint
from flask_restless import APIManager
from sqlalchemy.orm.attributes import InstrumentedAttribute
from flask_restless.helpers import *

sqlalchemy_swagger_type = {
    'INTEGER': 'integer',
    'SMALLINT': 'int32',
    'NUMERIC': 'number',
    'DECIMAL': 'number',
    'VARCHAR': 'string',
    'TEXT': 'string',
    'DATE': 'date',
    'TIME': 'date',
    'BOOLEAN': 'bool',
    'BLOB': 'binary',
    'BYTEA': 'binary',
    'BINARY': 'binary',
    'VARBINARY': 'binary',
    'FLOAT': 'float',
    'REAL': 'float',
    'DATETIME': 'date-time',
    'BIGINT': 'int64',
    'ENUM': 'string',
    'INTERVAL': 'date-time',
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
        'schemes': ['http'],
        'basePath': '/api/',
        'consumes': ['application/vnd.api+json'],
        'produces': ['application/vnd.api+json'],
        'paths': {},
        'definitions': {}
    }

    def __init__(self, app=None, **kwargs):
        self.app = None
        self.manager = None

        if app is not None:
            self.init_app(app, **kwargs)

    def to_json(self, **kwargs):
        return json.dumps(self.swagger, **kwargs)

    def to_yaml(self, **kwargs):
        return yaml.dump(self.swagger, **kwargs)

    def __str__(self):
        return self.to_json(indent=4)

    @property
    def version(self):
        if 'version' in self.swagger['info']:
            return self.swagger['info']['version']
        return None

    @version.setter
    def version(self, value):
        self.swagger['info']['version'] = value

    @property
    def title(self):
        if 'title' in self.swagger['info']:
            return self.swagger['info']['title']
        return None

    @title.setter
    def title(self, value):
        self.swagger['info']['title'] = value

    @property
    def description(self):
        if 'description' in self.swagger['info']:
            return self.swagger['info']['description']
        return None

    @description.setter
    def description(self, value):
        self.swagger['info']['description'] = value

    def add_path(self, model, **kwargs):
        name = model.__tablename__
        schema = model.__name__
        path = kwargs.get('url_prefix', "") + '/' + name.lower()
        id_path = "{0}/{{{1}Id}}".format(path, schema.lower())
        self.swagger['paths'][path] = {}

        for method in [m.lower() for m in kwargs.get('methods', ['GET'])]:
            if method == 'get':
                self.swagger['paths'][path][method] = {
                    'parameters': [{
                        'name': 'q',
                        'in': 'query',
                        'description': 'searchjson',
                        'type': 'string'
                    }],
                    'responses': {
                        200: {
                            'description': 'List ' + name.lower(),
                            'schema': {
                                'title': name.lower(),
                                'type': 'array',
                                'items': {'$ref': '#/definitions/' + name.lower()}
                            }
                        }
                    }
                }

                if model.__doc__:
                    self.swagger['paths'][path]['description'] = model.__doc__

                if id_path not in self.swagger['paths']:
                    self.swagger['paths'][id_path] = {}

                self.swagger['paths'][id_path][method] = {
                    'parameters': [{
                        'name': schema.lower() + 'Id',
                        'in': 'path',
                        'description': 'ID of ' + schema.lower(),
                        'required': True,
                        'type': 'integer'
                    }],
                    'responses': {
                        200: {
                            'description': 'Success ' + name.lower(),
                            'schema': {'title': name.lower(), '$ref': '#/definitions/' + name.lower()}
                        }
                    }
                }
                if model.__doc__:
                    self.swagger['paths'][id_path]['description'] = model.__doc__

            elif method == 'delete':
                if id_path not in self.swagger['paths']:
                    self.swagger['paths'][id_path] = {}

                self.swagger['paths']["{0}/{{{1}Id}}".format(path, schema.lower())][method] = {
                    'parameters': [{
                        'name': schema.lower() + 'Id',
                        'in': 'path',
                        'description': 'ID of ' + schema,
                        'required': True,
                        'type': 'integer'
                    }],
                    'responses': {200: {'description': 'Success'}}
                }
                if model.__doc__:
                    self.swagger['paths'][id_path]['description'] = model.__doc__
            else:
                self.swagger['paths'][path][method] = {
                    'parameters': [{
                        'name': name.lower(),
                        'in': 'body',
                        'description': schema,
                        'type': "#/definitions/" + schema.lower()
                    }],
                    'responses': {200: {'description': 'Success'}}
                }
                if model.__doc__:
                    self.swagger['paths'][path]['description'] = model.__doc__

    def add_defn(self, model, **kwargs):
        name = model.__name__
        self.swagger['definitions'][name.lower()] = {'type': 'object', 'properties': {}}
        columns = get_columns(model).keys()

        for column_name, column in get_columns(model).items():
            if column_name in kwargs.get('exclude_columns', []):
                continue
            try:

                column_type = str(column.type)
                if '(' in column_type:
                    column_type = column_type.split('(')[0]
                column_defn = sqlalchemy_swagger_type[column_type]

            except AttributeError:
                schema = get_related_model(model, column_name)

                if column_name + '_id' in columns:
                    column_defn = {'schema': {'$ref': schema.__name__.lower()}}
                else:
                    column_defn = {'schema': {'type': 'array', 'items': {'$ref': schema.__name__.lower()}}}

            if column.__doc__:
                column_defn['description'] = column.__doc__

            self.swagger['definitions'][name.lower()]['properties'][column_name] = column_defn

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
