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

"""The RequestHandler for /job URLs."""

import bson

import handlers.base as hbase
import handlers.common as hcommon
import handlers.response as hresponse
import models
import taskqueue.tasks as taskq
import utils.db


class JobHandler(hbase.BaseHandler):
    """Handle the /job URLs."""

    def __init__(self, application, request, **kwargs):
        super(JobHandler, self).__init__(application, request, **kwargs)

    @property
    def collection(self):
        return self.db[models.JOB_COLLECTION]

    @staticmethod
    def _valid_keys(method):
        return hcommon.JOB_VALID_KEYS.get(method, None)

    def _post(self, *args, **kwargs):
        response = hresponse.HandlerResponse(202)
        response.reason = "Request accepted and being imported"

        json_obj = kwargs["json_obj"]
        db_options = kwargs["db_options"]

        self.log.info(
            "Importing defconfigs for %s-%s",
            json_obj[models.JOB_KEY], json_obj[models.KERNEL_KEY])

        taskq.import_job.apply_async(
            [json_obj, db_options],
            link=[
                taskq.parse_build_log.s(json_obj, db_options)
            ]
        )

        return response

    def _delete(self, job_id, **kwargs):
        """Delete a job from the database.

        Use with care since documents cannot be retrieved after!

        Removing a job from the collection means to remove also all the
        other documents associated with the it: defconfig and subscription.

        :param job_id: The ID of the job to remove.
        :return Whatever is returned by the `utils.db.delete` function.
        """
        # TODO: maybe look into two-phase commits in mongodb
        # http://docs.mongodb.org/manual/tutorial/perform-two-phase-commits/
        response = hresponse.HandlerResponse()

        try:
            job_obj = bson.objectid.ObjectId(job_id)
            if utils.db.find_one(self.collection, [job_obj]):
                utils.db.delete(
                    self.db[models.DEFCONFIG_COLLECTION],
                    {models.JOB_ID_KEY: {"$in": [job_obj]}}
                )

                response.status_code = utils.db.delete(
                    self.collection, job_obj)
                if response.status_code == 200:
                    response.reason = "Resource '%s' deleted" % job_id
            else:
                response.status_code = 404
                response.reason = self._get_status_message(404)
        except bson.errors.InvalidId, ex:
            self.log.exception(ex)
            self.log.error("Invalid ID specified: %s", job_id)
            response.status_code = 400
            response.reason = "Wrong ID specified"

        return response
