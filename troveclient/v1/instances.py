# Copyright 2011 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from troveclient import base
from troveclient import common
from troveclient import exceptions

from swiftclient import client

REBOOT_SOFT = 'SOFT'
REBOOT_HARD = 'HARD'


def swift_client():
    auth_url = os.getenv("OS_AUTH_URL")
    user = os.getenv("OS_USERNAME")
    key = os.getenv("OS_PASSWORD")
    tenant = os.getenv("OS_TENANT_NAME")
    os_options = {'region_name': os.getenv("OS_REGION_NAME")}

    return client.Connection(auth_url, user, key, tenant_name=tenant,
                             auth_version="2.0", os_options=os_options)


class Instance(base.Resource):
    """An Instance is an opaque instance used to store Database instances."""
    def __repr__(self):
        return "<Instance: %s>" % self.name

    def list_databases(self):
        return self.manager.databases.list(self)

    def delete(self):
        """Delete the instance."""
        self.manager.delete(self)

    def restart(self):
        """Restart the database instance."""
        self.manager.restart(self.id)

    def detach_replica(self):
        """Stops the replica database from being replicated to."""
        self.manager.edit(self.id, detach_replica_source=True)


class Log(base.Resource):
    """A Log is a log on the database guest instance."""

    def __repr__(self):
        return "<Log: %s>" % self.name


class Instances(base.ManagerWithFind):
    """Manage :class:`Instance` resources."""
    resource_class = Instance

    log_cache = {}

    # TODO(SlickNik): Remove slave_of param after updating tests to replica_of
    def create(self, name, flavor_id, volume=None, databases=None, users=None,
               restorePoint=None, availability_zone=None, datastore=None,
               datastore_version=None, nics=None, configuration=None,
               replica_of=None, slave_of=None, replica_count=None):
        """Create (boot) a new instance."""

        body = {"instance": {
            "name": name,
            "flavorRef": flavor_id
        }}
        datastore_obj = {}
        if volume:
            body["instance"]["volume"] = volume
        if databases:
            body["instance"]["databases"] = databases
        if users:
            body["instance"]["users"] = users
        if restorePoint:
            body["instance"]["restorePoint"] = restorePoint
        if availability_zone:
            body["instance"]["availability_zone"] = availability_zone
        if datastore:
            datastore_obj["type"] = datastore
        if datastore_version:
            datastore_obj["version"] = datastore_version
        if datastore_obj:
            body["instance"]["datastore"] = datastore_obj
        if nics:
            body["instance"]["nics"] = nics
        if configuration:
            body["instance"]["configuration"] = configuration
        if replica_of or slave_of:
            body["instance"]["replica_of"] = base.getid(replica_of) or slave_of
        if replica_count:
            body["instance"]["replica_count"] = replica_count

        return self._create("/instances", body, "instance")

    def modify(self, instance, configuration=None):
        body = {
            "instance": {
            }
        }
        if configuration is not None:
            body["instance"]["configuration"] = configuration
        url = "/instances/%s" % base.getid(instance)
        resp, body = self.api.client.put(url, body=body)
        common.check_for_exceptions(resp, body, url)

    def edit(self, instance, configuration=None, name=None,
             detach_replica_source=False, remove_configuration=False):
        body = {
            "instance": {
            }
        }
        if configuration and remove_configuration:
            raise Exception("Cannot attach and detach configuration "
                            "simultaneously.")
        if remove_configuration:
            body["instance"]["configuration"] = None
        if configuration is not None:
            body["instance"]["configuration"] = configuration
        if name is not None:
            body["instance"]["name"] = name
        if detach_replica_source:
            # TODO(glucas): Remove slave_of after updating trove
            # (see trove.instance.service.InstanceController#edit)
            body["instance"]["slave_of"] = None
            body["instance"]["replica_of"] = None

        url = "/instances/%s" % base.getid(instance)
        resp, body = self.api.client.patch(url, body=body)
        common.check_for_exceptions(resp, body, url)

    def list(self, limit=None, marker=None, include_clustered=False):
        """Get a list of all instances.

        :rtype: list of :class:`Instance`.
        """
        return self._paginated("/instances", "instances", limit, marker,
                               {"include_clustered": include_clustered})

    def get(self, instance):
        """Get a specific instances.

        :rtype: :class:`Instance`
        """
        return self._get("/instances/%s" % base.getid(instance),
                         "instance")

    def backups(self, instance, limit=None, marker=None):
        """Get the list of backups for a specific instance.

        :rtype: list of :class:`Backups`.
        """
        url = "/instances/%s/backups" % base.getid(instance)
        return self._paginated(url, "backups", limit, marker)

    def delete(self, instance):
        """Delete the specified instance.

        :param instance: A reference to the instance to delete
        """
        url = "/instances/%s" % base.getid(instance)
        resp, body = self.api.client.delete(url)
        common.check_for_exceptions(resp, body, url)

    def _action(self, instance, body):
        """Perform a server "action" -- reboot/rebuild/resize/etc."""
        url = "/instances/%s/action" % base.getid(instance)
        resp, body = self.api.client.post(url, body=body)
        common.check_for_exceptions(resp, body, url)
        if body:
            return self.resource_class(self, body, loaded=True)
        return body

    def resize_volume(self, instance, volume_size):
        """Resize the volume on an existing instances."""
        body = {"resize": {"volume": {"size": volume_size}}}
        self._action(instance, body)

    def resize_instance(self, instance, flavor_id):
        """Resizes an instance with a new flavor."""
        body = {"resize": {"flavorRef": flavor_id}}
        self._action(instance, body)

    def restart(self, instance):
        """Restart the database instance.

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to restart.
        """
        body = {'restart': {}}
        self._action(instance, body)

    def configuration(self, instance):
        """Get a configuration on instances.

        :rtype: :class:`Instance`
        """
        return self._get("/instances/%s/configuration" % base.getid(instance),
                         "instance")

    def promote_to_replica_source(self, instance):
        """Promote a replica to be the new replica_source of its set

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to promote.
        """
        body = {'promote_to_replica_source': {}}
        self._action(instance, body)

    def eject_replica_source(self, instance):
        """Eject a replica source from its set

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to eject.
        """
        body = {'eject_replica_source': {}}
        self._action(instance, body)

    def log_list(self, instance):
        """Get a list of all guest logs.

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to get the log for.
        :rtype: list of :class:`GuestLog`.
        """
        url = '/instances/%s/log' % base.getid(instance)
        resp, body = self.api.client.get(url)
        common.check_for_exceptions(resp, body, url)
        return [Log(self, log, loaded=True) for log in body['logs']]

    def log_action(self, instance, log, enable=None, disable=None,
                   publish=None, discard=None):
        """Perform action on guest log.

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to get the log for.
        :param log: The type of <log> to publish
        :param enable: Turn on <log>
        :param disable: Turn off <log>
        :param publish: Publish log to associated container
        :param discard: Delete the associated container
        :rtype: List of :class:`Log`.
        """
        body = {"name": log}
        if enable:
            body.update({'enable': int(enable)})
        if disable:
            body.update({'disable': int(disable)})
        if publish:
            body.update({'publish': int(publish)})
        if discard:
            body.update({'discard': int(discard)})
        url = "/instances/%s/log" % base.getid(instance)
        resp, body = self.api.client.post(url, body=body)
        common.check_for_exceptions(resp, body, url)
        return Log(self, body['log'], loaded=True)

    def _get_container(self, instance, log, publish):
        try:
            if publish:
                log_info = self.log_action(instance, log, publish=True)
                container = log_info.container
            else:
                url = '/instances/%s/log-name/%s' % (base.getid(instance), log)
                resp, body = self.api.client.get(url)
                common.check_for_exceptions(resp, body, url)
                container = body['log-name']
            return container
        except client.ClientException:
            raise exceptions.GuestLogNotFoundError()

    def log_generator(self, instance, log, publish=None, lines=50,
                      swift=None):
        """Return generator to yield the last <lines> lines of guest log.

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to get the log for.
        :param log: The type of <log> to publish
        :param publish: Publish updates before displaying log
        :param lines: Display last <lines> lines of log (0 for all lines)
        :param swift: Connection to swift
        :rtype: generator function to yield log as chunks.
        """

        if not swift:
            swift = swift_client()

        def _log_generator(instance, log, publish, lines, swift):
            try:
                container = self._get_container(instance, log, publish)
                head, body = swift.get_container(container)
                log_obj_to_display = []
                if lines:
                    total_lines = lines
                    partial_results = False
                    parts = sorted(body, key=lambda obj: obj['last_modified'],
                                   reverse=True)
                    for part in parts:
                        obj_hdrs = swift.head_object(container, part['name'])
                        obj_lines = int(obj_hdrs['x-object-meta-lines'])
                        log_obj_to_display.insert(0, part)
                        if obj_lines >= lines:
                            partial_results = True
                            break
                        lines -= obj_lines
                    if not partial_results:
                        lines = total_lines
                    part = log_obj_to_display.pop(0)
                    hdrs, log_obj = swift.get_object(container, part['name'])
                    log_by_lines = log_obj.splitlines()
                    yield "\n".join(log_by_lines[-1 * lines:]) + "\n"
                else:
                    log_obj_to_display = sorted(
                        body, key=lambda obj: obj['last_modified'])
                for log_part in log_obj_to_display:
                    headers, log_obj = swift.get_object(container,
                                                        log_part['name'])
                    yield log_obj
            except client.ClientException:
                raise exceptions.GuestLogNotFoundError()

        return lambda: _log_generator(instance, log, publish, lines, swift)

    def log_save(self, instance, log, publish=None, filename=None):
        """Saves a guest log to a file.

        :param instance: The :class:`Instance` (or its ID) of the database
        instance to get the log for.
        :param log: The type of <log> to publish
        :param publish: Publish updates before displaying log
        :rtype: Filename to which log was saved
        """
        written_file = filename or (instance.name + '-' + log + ".log")
        log_gen = self.log_generator(instance, log, publish, 0)
        with open(written_file, 'w') as f:
            for log_obj in log_gen():
                f.write(log_obj)
        return written_file


class InstanceStatus(object):

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    BUILD = "BUILD"
    FAILED = "FAILED"
    REBOOT = "REBOOT"
    RESIZE = "RESIZE"
    SHUTDOWN = "SHUTDOWN"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    PROMOTING = "PROMOTING"
    EJECTING = "EJECTING"
    LOGGING = "LOGGING"