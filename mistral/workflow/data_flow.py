# -*- coding: utf-8 -*-
#
# Copyright 2013 - Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# TODO(rakhmerov): Take care of ad-hoc actions.

import copy
from oslo.config import cfg

from mistral import expressions as expr
from mistral.openstack.common import log as logging
from mistral.services import trusts
from mistral import utils


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def prepare_db_task(task_db, task_spec, upstream_task_specs, exec_db):
    """Prepare Data Flow properties ('in_context' and 'parameters')
     of given DB task.

    :param task_db: DB task to prepare.
    :param task_spec: Task specification.
    :param upstream_task_specs: Specifications of workflow upstream tasks.
    :param exec_db: Execution DB model.
    """

    upstream_db_tasks = [
        filter(lambda t: t.name == t_spec.get_name(), exec_db.tasks)[0]
        for t_spec in upstream_task_specs
    ]

    task_db.in_context = utils.merge_dicts(
        exec_db.context,
        _evaluate_upstream_context(upstream_db_tasks)
    )

    task_db.parameters = evaluate_task_parameters(
        task_spec,
        task_db.in_context
    )


def evaluate_task_parameters(task_spec, context):
    return expr.evaluate_recursively(task_spec.get_parameters(), context)


def _evaluate_upstream_context(upstream_db_tasks):
    ctx = {}

    for t_db in upstream_db_tasks:
        utils.merge_dicts(ctx, evaluate_outbound_context(t_db))

    return ctx


def evaluate_task_output(task_spec, raw_result):
    """Evaluates task output give a raw task result from action/workflow.

    :param task_spec: Task specification
    :param raw_result: Raw task result that comes from action/workflow
        (before publisher). Instance of mistral.workflow.base.TaskResult
    :return: Complete task output that goes to Data Flow context.
    """
    publish_dict = task_spec.get_publish()

    # Evaluate 'publish' clause using raw result as a context.
    output = expr.evaluate_recursively(publish_dict, raw_result.data) or {}

    # Add raw task result to task output under key 'task'
    output['task'] = {task_spec.get_name(): raw_result.data}

    return output


def evaluate_outbound_context(task_db):
    """Evaluates task outbound Data Flow context.

    This method assumes that complete task output (after publisher etc.)
    has already been evaluated.
    :param task_db: DB task.
    :return: Outbound task Data Flow context.
    """
    return utils.merge_dicts(
        copy.copy(task_db.in_context) or {},
        task_db.output
    )


def add_openstack_data_to_context(workbook_db, context):
    if context is None:
        context = {}

    if CONF.pecan.auth_enable:
        workbook_ctx = trusts.create_context(workbook_db)

        if workbook_ctx:
            context.update({'openstack': workbook_ctx.to_dict()})

    return context


def add_execution_to_context(exec_db, context):
    if context is None:
        context = {}

    context['__execution'] = {
        'id': exec_db.id,
        'wf_spec': exec_db['wf_spec'],
        'start_params': exec_db.start_params,
        'input': exec_db.input
    }

    return context