#!/usr/bin/python
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

import argparse
import datetime
import time
import sys

import models
import models.boot as mboot
import models.job as mjob
import models.defconfig as mdefconfig
import utils
import utils.db

ZERO_TIME = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)

# Data structures with old ID as the key, and new ID the value.
NEW_JOB_IDS = {}
NEW_DEFCONFIG_IDS = {}
DEFCONFIG_GIT_VAL = {}


def convert_job_collection(db, limit=0):
    count = db[models.JOB_COLLECTION].find().count()
    utils.LOG.info("Processing %s job documents", count)
    time.sleep(2)

    doc_count = 0
    for document in db[models.JOB_COLLECTION].find(limit=limit):
        doc_get = document.get

        if doc_get("version", None) == "1.0":
            continue
        else:
            doc_count += 1
            utils.LOG.info("Processing document #%s", doc_count)

            job = doc_get("job")
            kernel = doc_get("kernel")

            job_doc = mjob.JobDocument(job, kernel)
            job_doc.version = "1.0"
            job_doc.status = doc_get("status", "UNKNOWN")
            job_doc.created_on = doc_get("created_on")
            job_doc.private = doc_get("private", False)

            metadata = doc_get("metadata", None)
            if metadata:
                meta_get = metadata.get
                job_doc.git_url = meta_get("git_url", None)
                job_doc.git_commit = meta_get("git_commit", None)
                job_doc.git_branch = meta_get("git_branch", None)
                job_doc.git_describe = meta_get("git_describe", None)

            # Delete and save the old doc.
            ret_val = utils.db.delete(db[models.JOB_COLLECTION], doc_get("_id"))
            if ret_val != 200:
                utils.LOG.error(
                    "Error deleting job document %s", doc_get("_id")
                )
                time.sleep(3)
                sys.exit(1)

            ret_val, doc_id = utils.db.save(db, job_doc, manipulate=True)
            if ret_val == 201:
                NEW_JOB_IDS[job + "-" + kernel] = doc_id
            else:
                utils.LOG.error(
                    "Error saving new job document for %s", doc_get("_id"))
                time.sleep(3)
                sys.exit(1)

    count = db[models.JOB_COLLECTION].find().count()
    utils.LOG.info("Job documents at the end: %s (%s)", count, doc_count)
    time.sleep(2)


def convert_defconfig_collection(db, limit=0):

    count = db[models.DEFCONFIG_COLLECTION].find().count()
    utils.LOG.info("Processing %s defconfig documents", count)
    time.sleep(2)

    doc_count = 0
    for document in db[models.DEFCONFIG_COLLECTION].find(limit=limit):
        doc_get = document.get

        if doc_get("version", None) == "1.0":
            continue
        else:
            doc_count += 1
            utils.LOG.info("Processing document #%s", doc_count)

            metadata = doc_get("metadata", {})
            meta_get = metadata.get
            meta_pop = metadata.pop

            arch = None
            defconfig_full = None
            kconfig_fragments = None
            dirname = None

            job = doc_get("job")
            kernel = doc_get("kernel")
            defconfig = doc_get("defconfig")
            dirname = doc_get("dirname", None)

            if defconfig.startswith("arm-"):
                defconfig = defconfig.replace("arm-", "", 1)
                arch = "arm"
            elif defconfig.startswith("arm64-"):
                defconfig = defconfig.replace("arm64-", "", 1)
                arch = "arm64"
            elif defconfig.startswith("x86-"):
                defconfig = defconfig.replace("x86-", "", 1)
                arch = "x86"

            if arch is None and dirname is not None:
                if dirname.startswith("arm-"):
                    arch = "arm"
                elif dirname.startswith("arm64-"):
                    arch = "arm64"
                elif dirname.startswith("x86-"):
                    arch = "x86"

            if doc_get("arch", None) is not None:
                arch = doc_get("arch")
            if meta_get("arch", None) is not None:
                if arch != meta_get("arch"):
                    arch = meta_pop("arch")
            meta_pop("arch", None)
            if arch is None:
                utils.LOG.warn(
                    "arch is still None for %s-%s-%s", job, kernel, defconfig
                )
                arch = "arm"

            if meta_get("kconfig_fragments", None):
                kconfig_fragments = meta_pop("kconfig_fragments")
                fragment = \
                    kconfig_fragments.replace(
                        "frag-", "").replace(".config", "")
                if fragment not in defconfig:
                    defconfig_full = "+".join([defconfig, fragment])

            if not defconfig_full:
                defconfig_full = defconfig

            def_doc = mdefconfig.DefconfigDocument(
                job, kernel, defconfig, defconfig_full)

            def_doc.version = "1.0"
            def_doc.arch = arch
            def_doc.dirname = dirname
            def_doc.kconfig_fragments = kconfig_fragments
            def_doc.defconfig_full = defconfig_full
            def_doc.status = doc_get("status", models.UNKNOWN_STATUS)

            if not NEW_JOB_IDS.get(job + "-" + kernel, None):
                utils.LOG.error("No job ID for '%s-%s'", job, kernel)
            def_doc.job_id = NEW_JOB_IDS.get(job + "-" + kernel, None)

            def_doc.created_on = doc_get("created_on")

            def_doc.errors = doc_get("errors", 0)
            if def_doc.errors is None:
                def_doc.errors = 0
            else:
                def_doc.errors = int(def_doc.errors)
            def_doc.warnings = doc_get("warnings", 0)
            if def_doc.warnings is None:
                def_doc.warnings = 0
            else:
                def_doc.warnings = int(def_doc.warnings)
            def_doc.build_time = doc_get("build_time", 0)
            def_doc.modules_dir = doc_get("modules_dir", None)
            def_doc.modules = doc_get("modules", None)
            def_doc.build_log = doc_get("build_log", None)

            if metadata:
                if (str(def_doc.errors) != str(meta_get("build_errors")) and
                        meta_get("build_errors") is not None):
                    def_doc.errors = int(meta_pop("build_errors", 0))
                meta_pop("build_errors", 0)

                if (str(def_doc.warnings) != str(meta_get("build_warnings")) and
                        meta_get("build_warnings") is not None):
                    def_doc.warnings = int(meta_pop("build_warnings", 0))
                meta_pop("build_warnings", 0)

                def_doc.git_url = meta_pop("git_url", None)
                def_doc.git_branch = meta_pop("git_branch", None)
                def_doc.git_describe = meta_pop("git_describe", None)
                def_doc.git_commit = meta_pop("git_commit", None)
                def_doc.build_platform = meta_pop("build_platform", [])

                if meta_get("build_log", None):
                    def_doc.build_log = meta_get("build_log", None)
                meta_pop("build_log", None)

                if meta_get("build_result", None):
                    result = meta_get("build_result")
                    if result != def_doc.status:
                        def_doc.status = meta_pop("build_result")
                    else:
                        meta_pop("build_result")

                if str(meta_get("build_time")):
                    def_doc.build_time = meta_pop("build_time", 0)
                meta_pop("build_time", None)

                def_doc.dtb_dir = meta_pop("dtb_dir", None)
                def_doc.kernel_config = meta_pop("kernel_config", None)
                def_doc.kernel_image = meta_pop("kernel_image", None)
                def_doc.modules = meta_pop("modules", None)
                def_doc.system_map = meta_pop("system_map", None)
                def_doc.text_offset = meta_pop("text_offset", None)

                if meta_get("modules_dir", None):
                    def_doc.modules_dir = meta_pop("modules_dir")
                meta_pop("modules_dir", None)

                if meta_get("kconfig_fragments", None):
                    def_doc.kconfig_fragments = meta_pop("kconfig_fragments")
                meta_pop("kconfig_fragments", None)

                meta_pop("defconfig", None)
                meta_pop("job", None)

                def_doc.file_server_url = meta_pop("file_server_url", None)
                def_doc.file_server_resource = meta_pop(
                    "file_server_resource", None)

                if def_doc.file_server_resource is None:
                    def_doc.file_server_resource = (
                        "/" + job + "/" + kernel + "/" +
                        arch + "-" + defconfig_full
                    )

                def_doc.metadata = metadata

            ret_val = utils.db.delete(
                db[models.DEFCONFIG_COLLECTION], doc_get("_id")
            )
            if ret_val != 200:
                utils.LOG.error(
                    "Error deleting defconfig document %s", doc_get("_id")
                )
                time.sleep(3)
                sys.exit(1)

            if defconfig == "lab-tbaker-00":
                pass
            else:
                ret_val, doc_id = utils.db.save(db, def_doc, manipulate=True)
                if ret_val == 201:
                    key = job + "-" + kernel + "-" + defconfig_full + "-" + arch
                    NEW_DEFCONFIG_IDS[key] = \
                        (doc_id, defconfig, defconfig_full, arch)
                    DEFCONFIG_GIT_VAL[doc_id] = (
                        def_doc.git_branch, def_doc.git_url, def_doc.git_commit,
                        def_doc.git_describe
                    )
                else:
                    utils.LOG.error(
                        "Error saving new defconfig document for %s",
                        doc_get("_id")
                    )
                    time.sleep(3)
                    sys.exit(1)

    count = db[models.DEFCONFIG_COLLECTION].find().count()
    utils.LOG.info("Defconfig documents at the end: %s (%s)", count, doc_count)
    time.sleep(2)


def convert_boot_collection(db, lab_name, limit=0):

    count = db[models.BOOT_COLLECTION].find().count()
    utils.LOG.info("Processing %s boot documents", count)
    time.sleep(2)

    doc_count = 0
    for document in db[models.BOOT_COLLECTION].find(limit=limit):

        doc_get = document.get

        if doc_get("version", None) == "1.0":
            continue
        else:
            doc_count += 1
            utils.LOG.info("Processing document #%s", doc_count)

            board = doc_get("board")
            job = doc_get("job")
            kernel = doc_get("kernel")
            defconfig = doc_get("defconfig")
            metadata = doc_get("metadata", {})
            meta_get = metadata.get
            meta_pop = metadata.pop
            arch = None

            if defconfig.startswith("arm-"):
                defconfig = defconfig.replace("arm-", "", 1)
                arch = "arm"
            elif defconfig.startswith("arm64-"):
                defconfig = defconfig.replace("arm64-", "", 1)
                arch = "arm64"
            elif defconfig.startswith("x86-"):
                defconfig = defconfig.replace("x86-", "", 1)
                arch = "x86"
            else:
                arch = "arm"

            pre_lab = meta_pop("lab_name", None)
            if pre_lab:
                lab_name = pre_lab

            job_id = NEW_JOB_IDS.get(job + "-" + kernel, None)
            if not job_id:
                utils.LOG.error("No job ID found for %s-%s", job, kernel)

            defconfig_id, build_defconfig, defconfig_full, build_arch = \
                NEW_DEFCONFIG_IDS.get(
                    job + "-" + kernel + "-" + defconfig + "-" + arch,
                    [None, None, None, None]
                )

            def_full = meta_pop("defconfig_full", None)
            if def_full:
                utils.LOG.warn("Found defconfig_full")
                defconfig_full = def_full

            if build_arch is not None and arch != build_arch:
                utils.LOG.warn("Using build architecture")
                arch = build_arch

            if build_defconfig and defconfig != build_defconfig:
                defconfig = build_defconfig
            if not defconfig_full:
                defconfig_full = defconfig

            if not defconfig_id:
                utils.LOG.error(
                    "No defconfig ID found for %s-%s-%s (%s)",
                    job, kernel, defconfig, defconfig_full
                )

            boot_doc = mboot.BootDocument(
                board, job, kernel, defconfig, lab_name, defconfig_full, arch
            )

            boot_doc.job_id = job_id
            boot_doc.defconfig_id = defconfig_id
            boot_doc.version = "1.0"

            if defconfig_id:
                git_branch, git_url, git_commit, git_describe = \
                    DEFCONFIG_GIT_VAL.get(
                        defconfig_id, [None, None, None, None])
                boot_doc.git_branch = git_branch
                boot_doc.git_commit = git_commit
                boot_doc.git_describe = git_describe
                boot_doc.git_url = git_url

            boot_doc.created_on = doc_get("created_on", None)
            boot_doc.tine = doc_get("time", 0)
            if doc_get("warnings", None) is not None:
                boot_doc.warnings = int(doc_get("warnings"))
            boot_doc.status = doc_get("status", models.UNKNOWN_STATUS)
            boot_doc.boot_log = doc_get("boot_log", None)
            boot_doc.endianness = doc_get("endian", None)
            boot_doc.dtb = doc_get("dtb", None)
            boot_doc.dtb_addr = doc_get("dtb_addr", None)
            boot_doc.initrd_addr = doc_get("initrd_addr", None)
            boot_doc.load_addr = doc_get("load_addr", None)
            if doc_get("retries", None) is not None:
                boot_doc.retries = int(doc_get("retries"))
            boot_doc.boot_log_html = doc_get("boot_log_html", None)
            boot_doc.boot_log = doc_get("boot_log", None)
            boot_doc.kernel_image = doc_get("kernel_image", None)
            boot_doc.time = doc_get("time", ZERO_TIME)
            boot_doc.dtb_append = doc_get("dtb_append", None)

            if meta_get("fastboot", None) is not None:
                boot_doc.fastboot = meta_pop("fastboot")
            meta_pop("fastboot", None)

            boot_doc.fastboot_cmd = meta_pop("fastboot_cmd", None)
            boot_doc.boot_result_description = meta_pop(
                "boot_result_description", None)
            if not boot_doc.boot_log_html:
                boot_doc.boot_log_html = meta_pop("boot_log_html", None)
            if not boot_doc.boot_log:
                boot_doc.boot_log = meta_pop("boot_log", None)
            boot_doc.dtb_append = meta_pop("dtb_append", None)
            boot_doc.git_commit = meta_pop("git_commit", None)
            boot_doc.git_branch = meta_pop("git_branc", None)
            boot_doc.git_describe = meta_pop("git_describe", None)
            boot_doc.git_url = meta_pop("git_url", None)
            if meta_get("retries", None) is not None:
                boot_doc.retries = int(meta_pop("retries"))
            meta_pop("retries", None)
            meta_pop("version", None)

            if meta_get("arch", None) and not boot_doc.arch:
                boot_doc.arch = meta_pop("arch")

            boot_doc.file_server_resource = meta_pop(
                "file_server_resource", None)
            if not pre_lab and boot_doc.file_server_resource is None:
                boot_doc.file_server_resource = (
                    "/" + job + "/" + kernel + "/" +
                    arch + "-" + defconfig_full + "/"
                )

            boot_doc.board_instance = meta_pop("board_instance", None)
            boot_doc.initrd = meta_pop("initrd", None)

            boot_doc.file_server_url = meta_pop("file_server_url", None)

            boot_doc.metadata = metadata

            ret_val = utils.db.delete(
                db[models.BOOT_COLLECTION], doc_get("_id"))
            if ret_val != 200:
                utils.LOG.error(
                    "Error deleting boot document %s", doc_get("_id")
                )
                time.sleep(3)
                sys.exit(1)

            ret_val, doc_id = utils.db.save(db, boot_doc, manipulate=True)
            if ret_val != 201:
                utils.LOG.error(
                    "Error saving new boot document for %s",
                    doc_get("_id")
                )
                time.sleep(3)
                sys.exit(1)

    count = db[models.BOOT_COLLECTION].find().count()
    utils.LOG.info("Boot documents at the end: %s (%s)", count, doc_count)
    time.sleep(2)


def _check_func(db):
    """Check some documents if they are ok."""
    for document in db[models.JOB_COLLECTION].find(limit=3):
        print document
    for document in db[models.DEFCONFIG_COLLECTION].find(limit=3):
        print document
    for document in db[models.BOOT_COLLECTION].find(limit=3):
        print document


def main():
    parser = argparse.ArgumentParser(
        description="Convert mongodb data into new model",
        version=0.1
    )
    parser.add_argument(
        "--lab-name", "-n",
        type=str,
        help="The lab name to use for boot reports",
        required=True,
        dest="lab_name"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="The number of documents to process",
        dest="limit"
    )
    args = parser.parse_args()

    lab_name = args.lab_name
    limit = args.limit

    try:
        db = utils.db.get_db_connection({})
        convert_job_collection(db, limit)
        convert_defconfig_collection(db, limit)
        convert_boot_collection(db, lab_name, limit)
        _check_func(db)
    except KeyboardInterrupt:
        utils.LOG.info("User interrupted.")


if __name__ == "__main__":
    main()
