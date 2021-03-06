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

"""All the necessary functions to import test suites, sets and cases."""

import bson
import copy
import datetime
import types

import models
import models.test_case as mtcase
import models.test_set as mtset
import utils
import utils.db


def _add_error_message(errors_dict, error_code, error_msg):
    """Update an error data structure.

    :param errors_dict: The errors data structure.
    :type errors_dict: dict
    :param error_code: The error code.
    :type error_code: integer
    :param error_msg: The error message.
    :type error_msg: string
    """
    if error_code in errors_dict.keys():
        errors_dict[error_code].append(error_msg)
    else:
        errors_dict[error_code] = []
        errors_dict[error_code].append(error_msg)


def _get_document_and_update(oid, collection, fields, up_doc, validate_func):
    """Get the document and update the provided data structure.

    Perform a database search on the provided collection, searching for the
    passed `oid` retrieving the provided fields list.

    :param oid: The ID to search.
    :type oid: bson.objectid.ObjectId
    :param collection: The database collection where to search.
    :type collection: MongoClient
    :param fields: The fields to retrieve.
    :type fields: list
    :param up_doc: The document where to store the retrieved fields.
    :type up_doc: dict
    :param validate_func: A function used to validate the retrieved values.
    :type validate_func: function
    """
    doc = utils.db.find_one2(collection, oid, fields=fields)
    if doc:
        up_doc.update(
            {
                k: v
                for k, v in doc.iteritems()
                if validate_func(k, v)
            }
        )


def update_test_suite(suite_json, test_suite_id, db_options, **kwargs):
    """Perform update operations on the provided test suite.

    Search for missing values based on the other document keys.

    :param suite_json: The JSON object containing the test suite.
    :type suite_json: dict
    :param test_suite_id: The ID of the saved test suite.
    :type test_suite_id: string
    :param db_options: The database connection parameters.
    :type db_options: dict
    :return 200 if OK, 500 in case of error; the updated values from the test
    suite document as a dictionary.
    """
    ret_val = 200
    update_doc = {}
    local_suite = copy.deepcopy(suite_json)

    update_doc = _parse_test_suite(local_suite, db_options)
    if update_doc:
        database = utils.db.get_db_connection(db_options)
        ret_val = utils.db.update(
            database[models.TEST_SUITE_COLLECTION],
            {models.ID_KEY: bson.objectid.ObjectId(test_suite_id)},
            update_doc
        )

    return ret_val, update_doc


def _parse_test_suite(suite_json, db_options):
    """Parse the test suite JSON and retrieve the values to update.

    This is used to update a test suite when all its values are empty, but we
    have the defconfig_id, job_id, and/or boot_id.

    Not all values might be retrieved. This function parses the document only
    once and searches for the provided documents only once.

    If only the boot_id is provided, only the field available in that document
    will be update.

    :param suite_json: The JSON object.
    :type suite_json: dict
    :param db_options: The database connection options.
    :type db_options: dict
    :return A dictionary with the fields-values to update.
    """
    update_doc = {}
    suite_pop = suite_json.pop

    # The necessary values to link a test suite with its job, defconfig
    # and/or boot reports.
    defconfig_id = suite_pop(models.DEFCONFIG_ID_KEY, None)
    boot_id = suite_pop(models.BOOT_ID_KEY, None)
    job_id = suite_pop(models.JOB_ID_KEY, None)

    # The set of keys we need to update a test suite with to provide search
    # capabilities based on the values of the job, build and/or boot used.
    all_keys = set([
        models.ARCHITECTURE_KEY,
        models.BOARD_INSTANCE_KEY,
        models.BOARD_KEY,
        models.DEFCONFIG_FULL_KEY,
        models.DEFCONFIG_KEY,
        models.JOB_KEY,
        models.KERNEL_KEY
    ])

    def _get_valid_keys():
        """Parse the test suite JSON object and yield its keys.

        The yielded keys are those with a non-null value.
        """
        for k, v in suite_json.iteritems():
            if all([v is not None, v != "", v != "None"]):
                update_doc[k] = v
                yield k

    good_keys = set([f for f in _get_valid_keys()])
    missing_keys = list(all_keys - good_keys)

    # If we have at least one of the referenced documents, and we do not have
    # some of the values that make up a test_suite object, look for the
    # document and retrieve the values, then update the test suite.
    if all([missing_keys, any([defconfig_id, job_id, boot_id])]):
        def _update_missing_keys(key):
            """Remove a key from the needed one when we have a value for it.

            :param key: The key to remove.
            """
            missing_keys.remove(key)

        def _valid_doc_value(key, value):
            """Check that the value is valid (not null, or empty).

            If the value is valid, remove the key from the ones we need to
            get.

            :param key: The key whose value needs to be checked.
            :type key: string
            :param value: The value to check.
            :type value: string
            :return True or False.
            """
            is_valid = False
            if all([key in all_keys, value]):
                is_valid = True
                _update_missing_keys(key)
            return is_valid

        database = utils.db.get_db_connection(db_options)
        if defconfig_id:
            oid = bson.objectid.ObjectId(defconfig_id)
            update_doc[models.DEFCONFIG_ID_KEY] = oid

            _get_document_and_update(
                oid,
                database[models.DEFCONFIG_COLLECTION],
                missing_keys,
                update_doc,
                _valid_doc_value
            )

        # If we do not have any more missing keys, do not search further.
        if all([missing_keys, boot_id]):
            oid = bson.objectid.ObjectId(boot_id)
            update_doc[models.BOOT_ID_KEY] = oid

            _get_document_and_update(
                oid,
                database[models.BOOT_COLLECTION],
                missing_keys,
                update_doc,
                _valid_doc_value
            )

        if all([missing_keys, job_id]):
            oid = bson.objectid.ObjectId(job_id)
            update_doc[models.JOB_ID_KEY] = oid

            _get_document_and_update(
                oid,
                database[models.JOB_COLLECTION],
                missing_keys,
                update_doc,
                _valid_doc_value
            )
    else:
        if defconfig_id:
            update_doc[models.DEFCONFIG_ID_KEY] = \
                bson.objectid.ObjectId(defconfig_id)
        if boot_id:
            update_doc[models.BOOT_ID_KEY] = \
                bson.objectid.ObjectId(boot_id)
        if job_id:
            update_doc[models.JOB_ID_KEY] = \
                bson.objectid.ObjectId(job_id)

    return update_doc


def _import_multi_base(
        import_func, tests_list, suite_id, db_options, **kwargs):
    """Generic function to import a test sets or test cases list.

    The passed import function must be a function that is able to parse the
    specific test (either a test set or test case), and return a 3 values tuple
    as follows:
    0. The function return value as an integer.
    1. The ID of the saved document, or None if it has not been saved.
    2. An error message if an error occurred, or None.

    Additional named arguments passed might be (with the exact following
    names):
    * test_set_id
    * defconfig_id
    * job_id
    * job
    * kernel
    * defconfig
    * defconfig_full
    * lab_name
    * board
    * board_instance
    * mail_options

    :param import_func: The function that will be used to import each test
    object as found the test `tests_list` parameter.
    :type import_func: function
    :param tests_list: The list with the test sets or cases to import.
    :type tests_list: list
    :param suite_id: The ID of the test suite these test objects
    belong to.
    :param suite_id: string
    :param db_options: Options for connecting to the database.
    :type db_options: dict
    :return A list with the saved test objects IDs or an empty list; a
    dictionary with keys the error codes and value a list of error messages,
    or an empty dictionary.
    """
    database = utils.db.get_db_connection(db_options)
    err_results = {}
    test_ids = []
    res_keys = err_results.viewkeys()

    def _add_err_msg(err_code, err_msg):
        """Add error code and message to the data structure.

        :param err_code: The error code.
        :type err_code: integer
        :param err_msg: The error message.
        :"type err_msg: string
        """
        if err_code in res_keys:
            err_results[err_code].append(err_msg)
        else:
            err_results[err_code] = []
            err_results[err_code].append(err_msg)

    def _parse_result(ret_val, doc_id, err_msg):
        """Parse the result and its return value.

        :param ret_val: The return value of the test case import.
        :type ret_val: integer
        :param doc_id: The saved document ID.
        :type doc_id: bson.obectid.ObjectId
        :param err_msg: The error message.
        :type err_msg: string
        """
        if all([ret_val == 201, doc_id]):
            test_ids.append(doc_id)
        else:
            _add_err_msg(ret_val, err_msg)

    def _yield_tests_import():
        """Iterate through the test objects to import and return them.

        It will yield the results of the provided import function.
        """
        for test in tests_list:
            yield import_func(
                test, suite_id, database, db_options, **kwargs)

    [
        _parse_result(ret_val, doc_id, err_msg)
        for ret_val, doc_id, err_msg in _yield_tests_import()
    ]

    return test_ids, err_results


def _import_test_set(json_obj, suite_id, database, db_options, **kwargs):
    """Parse and save a test set.

    Additional named arguments passed might be (with the exact following
    names):
    * defconfig_id
    * job_id
    * job
    * kernel
    * defconfig
    * defconfig_full
    * lab_name
    * board
    * board_instance
    * mail_options
    * suite_name

    :param json_obj: The JSON data structure of the test sets to import.
    :type json_obj: dict
    :param suite_id: The ID of the test suite the test set belongs to.
    :type suite_id: bson.objectid.ObjectId
    :param database: The database connection.
    :param db_options: The database connection options.
    :type db_options: dict
    :return 200 if OK, 500 in case of errors; the saved document ID or None;
    an error message in case of error or None.
    """
    ret_val = 400
    error = None
    doc_id = None

    if isinstance(json_obj, types.DictionaryType):
        j_get = json_obj.get
        j_pop = json_obj.pop

        json_suite_id = j_get(models.TEST_SUITE_ID_KEY, None)
        cases_list = j_pop(models.TEST_CASE_KEY, [])

        if not json_suite_id:
            # Inject the suite_id value into the data structure.
            json_obj[models.TEST_SUITE_ID_KEY] = suite_id
        else:
            if json_suite_id == str(suite_id):
                # We want the ObjectId value, not the string.
                json_obj[models.TEST_SUITE_ID_KEY] = suite_id
            else:
                utils.LOG.warning(
                    "Test suite ID does not match the provided one")
                # XXX For now, force the suite_id value.
                json_obj[models.TEST_SUITE_ID_KEY] = suite_id

        try:
            test_name = j_get(models.NAME_KEY, None)
            test_set = mtset.TestSetDocument.from_json(json_obj)

            if test_set:
                test_set.created_on = datetime.datetime.now(
                    tz=bson.tz_util.utc)

                utils.LOG.info("Saving test set '%s'", test_name)
                ret_val, doc_id = utils.db.save(
                    database, test_set, manipulate=True)

                if ret_val != 201:
                    error = "Error saving test set '%s'" % test_name
                    utils.LOG.error(error)
                else:
                    if cases_list:
                        # XXX: need to handle errors here as well.
                        import_test_cases_from_test_set(
                            doc_id, suite_id, cases_list, db_options, **kwargs)
            else:
                error = "Missing mandatory key in JSON object"
        except ValueError, ex:
            error = (
                "Error parsing test set '%s': %s" % (test_name, ex.message))
            utils.LOG.exception(ex)
            utils.LOG.error(error)
    else:
        error = "Test set is not a valid JSON object"

    return ret_val, doc_id, error


def import_test_cases_from_test_set(
        test_set_id, suite_id, cases_list, db_options, **kwargs):
    """Import the test cases and update the test set.

    After importing the test cases, save the test set with their IDs.

    :param test_set_id: The ID of the test set.
    :type test_set_id: bson.objectid.ObjectId
    :param suite_id: The ID of the test suite.
    :type suite_id: bson.objectid.ObjectId
    :param cases_list: The list of test cases to import.
    :type cases_list: list
    :param db_options: The database connection options.
    :type db_options: dict
    """
    ret_val = 200
    errors = {}

    # Inject the test_set_id so that if we have test cases they will use it.
    kwargs[models.TEST_SET_ID_KEY] = test_set_id

    case_ids, errors = import_multi_test_cases(
        cases_list, suite_id, db_options, **kwargs)

    if case_ids:
        # Update the test set with the test case IDs.
        database = utils.db.get_db_connection()
        ret_val = utils.db.update(
            database[models.TEST_SET_COLLECTION],
            test_set_id,
            {models.TEST_CASE_KEY: case_ids}
        )
        if ret_val != 200:
            error_msg = (
                "Error saving test cases for test set '%s'" % test_set_id)
            _add_error_message(errors, ret_val, error_msg)
    else:
        ret_val = 500
        error_msg = "No test cases imported for test set '%s'", test_set_id
        utils.LOG.error(error_msg)
        _add_error_message(errors, ret_val, error_msg)

    return ret_val, errors


def import_multi_test_sets(set_list, suite_id, db_options, **kwargs):
    """Import all the test sets provided.

    Additional named arguments passed might be (with the exact following
    names):
    * defconfig_id
    * job_id
    * job
    * kernel
    * defconfig
    * defconfig_full
    * lab_name
    * board
    * board_instance
    * mail_options

    :param set_list: The list with the test sets to import.
    :type set_list: list
    :param suite_id: The ID of the test suite these test sets belong to.
    :param suite_id: bson.objectid.ObjectId
    :param db_options: Options for connecting to the database.
    :type db_options: dict
    :return A list with the saved test set IDs or an empty list; a dictionary
    with keys the error codes and value a list of error messages, or an empty
    dictionary.
    """
    return _import_multi_base(
        _import_test_set, set_list, suite_id, db_options, **kwargs)


def import_test_case(json_obj, suite_id, database, db_options, **kwargs):
    """Parse and save a test case.

    Additional named arguments passed might be (with the exact following
    names):
    * test_set_id
    * defconfig_id
    * job_id
    * job
    * kernel
    * defconfig
    * defconfig_full
    * lab_name
    * board
    * board_instance
    * mail_options

    :param json_obj: The JSON data structure of the test case to import.
    :type json_obj: dict
    :param suite_id: The ID of the test suite the test case belongs to.
    :type suite_id: bson.objectid.ObjectId
    :param database: The database connection.
    :param db_options: The database connection options.
    :type db_options: dict
    :return 200 if OK, 500 in case of errors; the saved document ID or None;
    an error message in case of error or None.
    """
    ret_val = 400
    error = None
    doc_id = None

    if isinstance(json_obj, types.DictionaryType):
        j_get = json_obj.get
        json_suite_id = j_get(models.TEST_SUITE_ID_KEY, None)
        if not json_suite_id:
            # Inject the suite_id value into the data structure.
            json_obj[models.TEST_SUITE_ID_KEY] = suite_id
        else:
            if json_suite_id == str(suite_id):
                json_obj[models.TEST_SUITE_ID_KEY] = suite_id
            else:
                utils.LOG.warning(
                    "Test suite ID does not match the provided one")
                # XXX For now, force the suite_id value.
                json_obj[models.TEST_SUITE_ID_KEY] = suite_id

        try:
            test_name = j_get(models.NAME_KEY, None)
            test_case = mtcase.TestCaseDocument.from_json(json_obj)

            if test_case:
                k_get = kwargs.get

                test_case.created_on = datetime.datetime.now(
                    tz=bson.tz_util.utc)
                test_case.test_set_id = k_get(models.TEST_SET_ID_KEY, None)

                utils.LOG.info("Saving test case '%s'", test_name)
                ret_val, doc_id = utils.db.save(
                    database, test_case, manipulate=True)

                if ret_val != 201:
                    error = "Error saving test case '%s'" % test_name
                    utils.LOG.error(error)
            else:
                error = "Missing mandatory key in JSON object"
        except ValueError, ex:
            error = (
                "Error parsing test case '%s': %s" % (test_name, ex.message))
            utils.LOG.exception(ex)
            utils.LOG.error(error)
    else:
        error = "Test case is not a valid JSON object"

    return ret_val, doc_id, error


def import_multi_test_cases(case_list, suite_id, db_options, **kwargs):
    """Import all the test cases provided.

    Additional named arguments passed might be (with the exact following
    names):
    * test_set_id
    * defconfig_id
    * job_id
    * job
    * kernel
    * defconfig
    * defconfig_full
    * lab_name
    * board
    * board_instance
    * mail_options

    :param case_list: The list with the test cases to import.
    :type case_list: list
    :param suite_id: The ID of the test suite these test cases belong to.
    :param suite_id: string
    :param db_options: Options for connecting to the database.
    :type db_options: dict
    :return A list with the saved test case IDs or an empty list; a dictionary
    with keys the error codes and value a list of error messages, or an empty
    dictionary.
    """
    return _import_multi_base(
        import_test_case, case_list, suite_id, db_options, **kwargs)
