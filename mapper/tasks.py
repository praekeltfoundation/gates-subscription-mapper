from __future__ import absolute_import, unicode_literals
from celery.task import Task


class TestTask(Task):
    def run(self, **kwargs):
        return "Successful"


test_task = TestTask()
