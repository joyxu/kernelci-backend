# Copyright (C) 2014 Linaro Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Handle the /count URLs used to count objects in the database."""

import tornado.gen

import handlers.base as hbase
import handlers.common as hcommon
import handlers.response as hresponse
import models
import utils.db

# Internally used only. It is used to retrieve just one field for
# the query results since we only need to count the results, we are
# not interested in the values.
COUNT_FIELDS = {models.ID_KEY: True}


class CountHandler(hbase.BaseHandler):
    """Handle the /count URLs."""

    def __init__(self, application, request, **kwargs):
        super(CountHandler, self).__init__(application, request, **kwargs)

    @staticmethod
    def _valid_keys(method):
        return hcommon.COUNT_VALID_KEYS.get(method, None)

    def _get_one(self, collection, **kwargs):
        response = hresponse.HandlerResponse()

        if collection in hcommon.COLLECTIONS.keys():
            response.result = count_one_collection(
                self.db[hcommon.COLLECTIONS[collection]],
                collection,
                self.get_query_arguments,
                self._valid_keys("GET")
            )
        else:
            response.status_code = 404
            response.reason = "Collection %s not found" % collection

        return response

    def _get(self, **kwargs):
        response = hresponse.HandlerResponse()
        response.result = count_all_collections(
            self.db,
            self.get_query_arguments,
            self._valid_keys("GET")
        )

        return response

    @tornado.gen.coroutine
    def post(self, *args, **kwargs):
        """Not implemented."""
        self.write_error(status_code=501)

    @tornado.gen.coroutine
    def delete(self, *args, **kwargs):
        """Not implemented."""
        self.write_error(status_code=501)


def count_one_collection(
        collection, collection_name, query_args_func, valid_keys):
    """Count all the available documents in the provide collection.

    :param collection: The collection whose elements should be counted.
    :param collection_name: The name of the collection to count.
    :type collection_name: str
    :param query_args_func: A function used to return a list of the query
    arguments.
    :type query_args_func: function
    :param valid_keys: A list containing the valid keys that should be
    retrieved.
    :type valid_keys: list
    :return A list containing a dictionary with the `collection`, `count` and
    optionally the `fields` fields.
    """
    result = []
    spec = hcommon.get_query_spec(query_args_func, valid_keys)
    hcommon.get_and_add_date_range(spec, query_args_func)
    hcommon.update_id_fields(spec)

    if spec:
        _, number = utils.db.find_and_count(
            collection, 0, 0, spec, COUNT_FIELDS)
        if not number:
            number = 0

        result.append(dict(collection=collection_name, count=number))
    else:
        result.append(
            dict(
                collection=collection_name,
                count=utils.db.count(collection))
        )

    return result


def count_all_collections(database, query_args_func, valid_keys):
    """Count all the available documents in the database collections.

    :param database: The datase connection to use.
    :param query_args_func: A function used to return a list of the query
    arguments.
    :type query_args_func: function
    :param valid_keys: A list containing the valid keys that should be
    retrieved.
    :type valid_keys: list
    :return A list containing a dictionary with the `collection` and `count`
    fields.
    """
    result = []

    spec = hcommon.get_query_spec(query_args_func, valid_keys)
    hcommon.get_and_add_date_range(spec, query_args_func)
    hcommon.update_id_fields(spec)

    if spec:
        for key, val in hcommon.COLLECTIONS.iteritems():
            _, number = utils.db.find_and_count(
                database[val], 0, 0, spec, COUNT_FIELDS)
            if not number:
                number = 0
            result.append(dict(collection=key, count=number))
    else:
        for key, val in hcommon.COLLECTIONS.iteritems():
            result.append(
                dict(
                    collection=key,
                    count=utils.db.count(database[val]))
            )

    return result
