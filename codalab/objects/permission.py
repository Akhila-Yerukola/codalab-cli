'''
Defines ORM classes for groups and permissions.
'''
from codalab.model.orm_object import ORMObject
from codalab.common import (
    precondition,
    UsageError,
    PermissionError,
)
from codalab.lib import (
    spec_util,
)
from codalab.model.tables import (
    GROUP_OBJECT_PERMISSION_ALL,
    GROUP_OBJECT_PERMISSION_READ,
    GROUP_OBJECT_PERMISSION_NONE
)
from codalab.model.util import LikeQuery

class Group(ORMObject):
    '''
    Defines a group object which is used to assign permissions to a set of users.
    '''
    COLUMNS = ('uuid', 'name', 'owner_id', 'user_defined')

    def validate(self):
        '''
        Check a number of basic conditions that would indicate serious errors if
        they do not hold. Right now, validation only checks this worksheet's uuid
        and its name.
        '''
        spec_util.check_uuid(self.uuid)
        spec_util.check_name(self.name)
        precondition(isinstance(self.owner_id, basestring), 'Invalid value: owner_id.')
        precondition(isinstance(self.user_defined, bool), 'Invalid value: user_defined.')

    def __repr__(self):
        return 'Group(uuid=%r, name=%r)' % (self.uuid, self.name)

    def update_in_memory(self, row, strict=False):
        if strict:
            if 'uuid' not in row:
                row['uuid'] = spec_util.generate_uuid()
        super(Group, self).update_in_memory(row)

############################################################

def unique_group(model, group_spec, user_id):
    '''
    Return a group_info corresponding to |group_spec|.
    If |user_id| is given, only search only group that the user is involved in
    (either as an owner or just as a regular member).
    Otherwise, search all groups (this happens when we're root).
    '''
    def search_all(model, **spec_filters):
        return model.batch_get_groups(**spec_filters)
    def search_user(model, **spec_filters):
        return model.batch_get_all_groups(
            spec_filters,
            {'owner_id': user_id, 'user_defined': True},
            {'user_id': user_id})
    if user_id == None:
        search = search_all
    else:
        search = search_user
    return get_single_group(model, group_spec, search)

def get_single_group(model, group_spec, search_fn):
    '''
    Helper function.
    Resolve a string group_spec to a unique group for the given |search_fn|.
    Throw an error if zero or more than one group matches.
    '''
    if not group_spec:
        raise UsageError('Tried to expand empty group_spec!')
    if spec_util.UUID_REGEX.match(group_spec):
        groups = search_fn(model, uuid=group_spec)
        message = "uuid starting with '%s'" % (group_spec,)
    elif spec_util.UUID_PREFIX_REGEX.match(group_spec):
        groups = search_fn(model, uuid=LikeQuery(group_spec + '%'))
        message = "uuid starting with '%s'" % (group_spec,)
    else:
        spec_util.check_name(group_spec)
        groups = search_fn(model, name=group_spec)
        message = "name '%s'" % (group_spec,)
    if not groups:
        raise UsageError('Found no group with %s' % (message,))
    elif len(groups) > 1:
        raise UsageError(
          'Found multiple groups with %s:%s' %
          (message, ''.join('\n  uuid=%s' % (group['uuid'],) for group in groups))
        )
    return groups[0]

############################################################
# Checking permissions for worksheets

def _check_permission(model, user, obj, need_permission):
    have_permission = model.get_user_permission(user.unique_id if user else None, obj.uuid, obj.owner_id)
    #print '_check_permission %s %s, have %s, need %s' % (user, obj, permission_str(have_permission), permission_str(need_permission))
    if have_permission >= need_permission:
        return
    if user:
        user_str = '%s(%s)' % (user.name, user.unique_id)
    else:
        user_str = None
    raise PermissionError("User %s does not have sufficient permissions on %s(%s) (have %s, need %s)." % \
        (user_str, obj.name, obj.uuid, permission_str(have_permission), permission_str(need_permission)))

def check_has_read_permission(model, user, obj):
    _check_permission(model, user, obj, GROUP_OBJECT_PERMISSION_READ)
def check_has_all_permission(model, user, obj):
    _check_permission(model, user, obj, GROUP_OBJECT_PERMISSION_ALL)

############################################################
# Checking permissions for bundles

def _check_permission_on_bundles(model, user, bundle_uuids, need_permission):
    if len(bundle_uuids) == 0:
        return
    have_permissions = model.get_user_permission_on_bundles(user.unique_id if user else None, bundle_uuids)
    #print '_check_permission_on_bundles %s %s, have %s, need %s' % (user, bundle_uuids, map(permission_str, have_permissions), permission_str(need_permission))
    if min(have_permissions) >= need_permission:
        return
    if user:
        user_str = '%s(%s)' % (user.name, user.unique_id)
    else:
        user_str = None
    raise PermissionError("User %s does not have sufficient permissions on bundles %s (have %s, need %s)." % \
        (user_str, bundle_uuids, map(permission_str, have_permissions), permission_str(need_permission)))

def check_has_read_permission_on_bundles(model, user, bundle_uuids):
    _check_permission_on_bundles(model, user, bundle_uuids, GROUP_OBJECT_PERMISSION_READ)
def check_has_all_permission_on_bundles(model, user, bundle_uuids):
    _check_permission_on_bundles(model, user, bundle_uuids, GROUP_OBJECT_PERMISSION_ALL)

############################################################
# Parsing functions for permissions.

def parse_permission(permission_str):
    if 'r' == permission_str or 'read' == permission_str:
        return GROUP_OBJECT_PERMISSION_READ
    if 'a' == permission_str or 'all' == permission_str:
        return GROUP_OBJECT_PERMISSION_ALL
    if 'n' == permission_str or 'none' == permission_str:
        return GROUP_OBJECT_PERMISSION_NONE
    raise UsageError("Invalid permission flag specified (%s)" % (permission_str))

def permission_str(permission):
    if permission == 0: return 'none'
    if permission == 1: return 'read'
    if permission == 2: return 'all'
    raise UsageError("Invalid permission: %s" % permission)

# [{'group_name':'a', 'permission:1}, {'group_name':'b', 'permission':2}] => 'a:read,b:all'
def group_permissions_str(group_permissions):
    if len(group_permissions) == 0:
        return '-'
    return ','.join(
            '%s(%s):%s' % (row['group_name'], row['group_uuid'][0:8], permission_str(row['permission']))
    for row in group_permissions)
