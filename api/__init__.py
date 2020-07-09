# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 10:47:13 2020

@author: Julia Schroeder, julia.schroeder@grammm.com
@copyright: _Placeholder_copyright_
"""

from flask import Flask, jsonify, request, make_response

import yaml
from openapi_core import create_spec
from openapi_core.shortcuts import RequestValidator, ResponseValidator
from openapi_core.wrappers.flask import FlaskOpenAPIRequest, FlaskOpenAPIResponse
from sqlalchemy.exc import DatabaseError, OperationalError
from functools import wraps
import traceback

from tools.config import Config

BaseRoute = "/api/v1"  # Common prefix for all endpoints

apiVersion = None  # API specification version. Extracted from the OpenAPI document.
backendVersion = "0.2.3"  # Backend version number


def _loadOpenAPISpec():
    """Load OpenAPI specification from 'res/openapi.yaml'.

    Load specification, extract version number and create Request- and ResponseValidators
    """
    with open("res/openapi.yaml", "r") as file:
        openapi_defs = yaml.load(file, Loader=yaml.SafeLoader)
    if "servers" in Config["openapi"]:
        openapi_defs["servers"] += Config["openapi"]["servers"]
    spec = create_spec(openapi_defs)
    global apiVersion
    apiVersion = openapi_defs["info"]["version"]
    return RequestValidator(spec), ResponseValidator(spec)


API = Flask("MI-API")  # Core API object
API.config["JSON_SORT_KEYS"] = False  # Do not sort response fields. Crashes when returning lists...
requestValidator, responseValidator = _loadOpenAPISpec()


def validateRequest(flask_request):
    """Validate the request

    Parameters
    ----------
    flask_request: flask.request
        The request sent by flask

    Returns
    -------
    Boolean
        True if the request is valid, False otherwise
    string
        Error message if validation failed, None otherwise"""
    result = requestValidator.validate(FlaskOpenAPIRequest(flask_request))
    if result.errors:
        return False, jsonify(message="Bad Request", errors=[type(error).__name__ for error in result.errors]), result.errors
    return True, None, None


def secure(requireDB=False, requireAuth=True):
    """Decorator securing API functions

       Arguments:
           - requireDB (boolean)
               Whether the database is needed for the call. If set to True and the database is not configured,
               and error message is returned without invoking the endpoint.

       Automatically validates the request using the OpenAPI specification and returns a HTTP 400 to the client if validation
       fails. Also validates the response generated by the endpoint and returns a HTTP 500 on error. This behavior can be
       deactivated in the configuration.

       If an exception is raised during execution, a HTTP 500 message is returned to the client and a short description of the
       error is sent in the 'error' field of the response."""
    from .security import getSecurityContext
    def inner(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def call():
                ret = func(*args, **kwargs)
                response = make_response(ret)
                try:
                    result = responseValidator.validate(FlaskOpenAPIRequest(request), FlaskOpenAPIResponse(response))
                except AttributeError:
                    result = None
                if result is not None and result.errors:
                    if Config["openapi"]["validateResponse"]:
                        API.logger.error("Response validation failed: "+str(result.errors))
                        return jsonify(message="The server generated an invalid response."), 500
                    else:
                        API.logger.warn("Response validation failed: "+str(result.errors))
                return ret

            if requireAuth:
                error = getSecurityContext()
                if error is not None:
                    return jsonify(message="Access denied", error=error), 403
            valid, message, errors = validateRequest(request)
            if not valid:
                if Config["openapi"]["validateRequest"]:
                    API.logger.info("Request validation failed: {}".format(errors))
                    return message, 400
                else:
                    API.logger.warn("Request validation failed: {}".format(errors))

            if requireDB:
                from orm import DB
                if DB is None:
                    return jsonify(message="Database not available."), 503
            try:
                return call()
            except DatabaseError as err:
                API.logger.error("Database query failed: {}".format(err))
                return jsonify(message="Database error."), 503
            except:
                API.logger.error(traceback.format_exc())
                return jsonify(message="The server encountered an error while processing the request."), 500
        return wrapper
    return inner


@API.after_request
def noCache(response):
    """Add no-cache headers to the response"""
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.max_age = 1
    return response


from . import errors
