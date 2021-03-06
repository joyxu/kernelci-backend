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

"""Test module for the BatchHandler handler."""

import concurrent.futures
import json
import mock
import mongomock
import tornado
import tornado.testing

import handlers.app
import urls

# Default Content-Type header returned by Tornado.
DEFAULT_CONTENT_TYPE = 'application/json; charset=UTF-8'


class TestBatchHandler(
        tornado.testing.AsyncHTTPTestCase, tornado.testing.LogTrapTestCase):

    def setUp(self):
        self.mongodb_client = mongomock.Connection()
        super(TestBatchHandler, self).setUp()

        patched_find_token = mock.patch(
            "handlers.base.BaseHandler._find_token")
        self.find_token = patched_find_token.start()
        self.find_token.return_value = "token"

        patched_validate_token = mock.patch("handlers.common.validate_token")
        self.validate_token = patched_validate_token.start()
        self.validate_token.return_value = (True, "token")

        self.addCleanup(patched_find_token.stop)
        self.addCleanup(patched_validate_token.stop)

    def get_app(self):
        dboptions = {
            'dbpassword': "",
            'dbuser': ""
        }

        settings = {
            'dboptions': dboptions,
            'client': self.mongodb_client,
            'executor': concurrent.futures.ThreadPoolExecutor(max_workers=2),
            'default_handler_class': handlers.app.AppHandler,
            'debug': False
        }

        return tornado.web.Application([urls._BATCH_URL], **settings)

    def get_new_ioloop(self):
        return tornado.ioloop.IOLoop.instance()

    def test_delete_no_token(self):
        response = self.fetch('/batch', method='DELETE')
        self.assertEqual(response.code, 501)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_delete_with_token(self):
        headers = {'Authorization': 'foo'}

        response = self.fetch(
            '/batch', method='DELETE', headers=headers,
        )

        self.assertEqual(response.code, 501)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_get_no_token(self):
        response = self.fetch('/batch', method='GET')
        self.assertEqual(response.code, 501)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_get_with_token(self):
        headers = {'Authorization': 'foo'}

        response = self.fetch(
            '/batch', method='GET', headers=headers,
        )

        self.assertEqual(response.code, 501)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_post_without_token(self):
        self.find_token.return_value = None

        batch_dict = {
            "batch": [
                {"method": "GET", "collection": "count", "operation_id": "foo"}
            ]
        }
        body = json.dumps(batch_dict)

        response = self.fetch('/batch', method='POST', body=body)

        self.assertEqual(response.code, 403)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_post_not_json_content(self):
        headers = {'Authorization': 'foo', 'Content-Type': 'application/json'}

        response = self.fetch(
            '/batch', method='POST', body='', headers=headers
        )

        self.assertEqual(response.code, 422)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_post_wrong_content_type(self):
        headers = {'Authorization': 'foo'}

        response = self.fetch(
            '/batch', method='POST', body='', headers=headers
        )

        self.assertEqual(response.code, 415)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    def test_post_wrong_json(self):
        headers = {'Authorization': 'foo', 'Content-Type': 'application/json'}

        body = json.dumps(dict(foo='foo', bar='bar'))

        response = self.fetch(
            '/batch', method='POST', body=body, headers=headers
        )

        self.assertEqual(response.code, 400)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)

    @mock.patch("taskqueue.tasks.run_batch_group")
    def test_post_correct(self, mocked_run_batch):
        headers = {'Authorization': 'foo', 'Content-Type': 'application/json'}
        batch_dict = {
            "batch": [
                {"method": "GET", "collection": "count", "operation_id": "foo"}
            ]
        }
        body = json.dumps(batch_dict)

        mocked_run_batch.return_value = {}

        response = self.fetch(
            '/batch', method='POST', body=body, headers=headers
        )

        self.assertEqual(response.code, 200)
        self.assertEqual(
            response.headers['Content-Type'], DEFAULT_CONTENT_TYPE)
        mocked_run_batch.assert_called_once_with(
            [
                {
                    'operation_id': 'foo',
                    'method': 'GET',
                    'collection': 'count'
                }
            ],
            {
                'dbuser': '',
                'dbpassword': ''
            }
        )
