# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2020 grommunio GmbH

from flask import Flask, jsonify, request, make_response
from functools import wraps

from orm import DB
from services import Service
from tools.config import Config

import openapi_core
from openapi_core.shortcuts import RequestValidator, ResponseValidator
if openapi_core.__version__.split(".") < ["0", "13", "0"]:
    from openapi_core.wrappers.flask import FlaskOpenAPIRequest, FlaskOpenAPIResponse
else:
    from openapi_core.contrib.flask import FlaskOpenAPIRequest, FlaskOpenAPIResponse

from . import apiSpec


if "servers" in Config["openapi"]:
    apiSpec["servers"] += Config["openapi"]["servers"]
apiSpec = openapi_core.create_spec(apiSpec)
requestValidator, responseValidator = RequestValidator(apiSpec), ResponseValidator(apiSpec)


API = Flask("grommunio Admin API")  # Core API object
API.config["JSON_SORT_KEYS"] = False  # Do not sort response fields. Crashes when returning lists...
if DB is not None:
    DB.enableFlask(API)

if not Config["openapi"]["validateRequest"]:
    API.logger.warning("Request validation is disabled!")
if not Config["openapi"]["validateResponse"]:
    API.logger.warning("Response validation is disabled!")


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


def reloadORM():
    """Reload all active orm modules."""
    import importlib
    import sys
    API.logger.warn("Database schema version updated detected - reloading ORM")
    DB.initVersion()
    for name, module in [(name, module) for name, module in sys.modules.items() if name.startswith("orm.")]:
        importlib.reload(module)


def secure(requireDB=False, requireAuth=True, authLevel="basic", service=None, validateCSRF=None):
    """Decorator securing API functions.

       Arguments:
           - requireDB (boolean or int)
               Whether the database is needed for the call. If set to True and the database is not configured,
               and error message is returned without invoking the endpoint. If given as an integer, marks the minimum required
               schema version.
           - requireAuth (boolean or "optional")
               Whether authentication is required to use this endpoint. When set to False, no login context is created
               and user information is not available, even if logged in.
           - authLevel ("basic" or "user")
               Create login context with user object ("user") or only with information from token ("basic").
               User information can be loaded later if necessary.
           - service (string)
               Execute this endpoint in a service context. The service object is passed to the endpoint function
               as the last (unnamed) parameter.
           - validateCSRF (bool or None)
               Validate CSRF token. None will enable validation for non-GET methods.

       Automatically validates the request using the OpenAPI specification and returns a HTTP 400 to the client if validation
       fails. Also validates the response generated by the endpoint and returns a HTTP 500 on error. This behavior can be
       deactivated in the configuration.

       If an exception is raised during execution, a HTTP 500 message is returned to the client and a short description of the
       error is sent in the 'error' field of the response.
       """
    from .security import getSecurityContext

    def inner(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def call():
                if service:
                    with Service(service) as srv:
                        ret = func(*args, srv, **kwargs)
                else:
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
                checkCSRF = False if Config["security"].get("disableCSRF") else validateCSRF
                error = getSecurityContext(authLevel, checkCSRF)
                if error is not None and requireAuth != "optional":
                    return jsonify(message="Access denied", error=error), 401
            valid, message, errors = validateRequest(request)
            if not valid:
                if Config["openapi"]["validateRequest"]:
                    API.logger.info("Request validation failed: {}".format(errors))
                    return message, 400
                else:
                    API.logger.warn("Request validation failed: {}".format(errors))

            if requireDB or requireAuth:
                if DB is None:
                    return jsonify(message="Database not available."), 503
                if DB.requireReload():
                    reloadORM()
                if isinstance(requireDB, int) and not isinstance(requireDB, bool) and DB.version < requireDB:
                    return jsonify(message="Database schema version too old. Please update to at least n{}."
                                   .format(requireDB)), 500
            return call()
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
