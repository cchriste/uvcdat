############################################################################
##
## Copyright (C) 2006-2007 University of Utah. All rights reserved.
##
## This file is part of VisTrails.
##
## This file may be used under the terms of the GNU General Public
## License version 2.0 as published by the Free Software Foundation
## and appearing in the file LICENSE.GPL included in the packaging of
## this file.  Please review the following to ensure GNU General Public
## Licensing requirements will be met:
## http://www.opensource.org/licenses/gpl-license.php
##
## If you are unsure which license is appropriate for your use (for
## instance, you are interested in developing a commercial derivative
## of VisTrails), please contact us at vistrails@sci.utah.edu.
##
## This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
## WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
##
############################################################################

from db.domain import DBWorkflow, DBAdd, DBDelete, DBAction
import copy
import datetime
import getpass

def updateIdScope(vistrail):
    for action in vistrail.db_actions.itervalues():
        vistrail.idScope.updateBeginId('action', action.db_id+1)
        for operation in action.db_operations:
            vistrail.idScope.updateBeginId('operation', operation.db_id+1)
            if operation.vtType == 'add' or operation.vtType == 'change':
                # update ids of data
                vistrail.idScope.updateBeginId(operation.db_what, 
                                               getNewObjId(operation)+1)

def materializeWorkflow(vistrail, version):
    # construct path up through tree and perform each action
    if vistrail.db_get_action(version) is not None:
        workflow = DBWorkflow()
        #	    for action in getActionChain(vistrail, version):
        #		oldPerformAction(action, workflow)
        performActions(getActionChain(vistrail, version), 
                            workflow)
        workflow.db_id = version
        workflow.db_vistrailId = vistrail.db_id
        return workflow
    elif version == 0:
        return DBWorkflow()

def getActionChain(vistrail, version, start=0):
    result = []
    currentId = version
    while currentId > start: #and currentId > 0:
        action = vistrail.db_get_action(currentId)
        result.append(action)
        currentId = action.db_prevId
    result.reverse()
    return result

def getCurrentOperationDict(actions, currentOperations=None):
    if currentOperations is None:
        currentOperations = {}

    # note that this operation assumes unique ids for each operation's data
    # any add adds to the dict, delete removes from the dict, and
    # change replaces the current value in the dict
    for action in actions:
        print 'action: %d' % action.db_id
        for operation in action.db_operations:
            if operation.vtType == 'add':
                print "add: %s %s" % (operation.db_what, 
                                      operation.db_objectId)
                print "    to:  %s %s" % (operation.db_parentObjType, operation.db_parentObjId)
                currentOperations[(operation.db_what, 
                                   operation.db_objectId)] = \
                                   operation
            elif operation.vtType == 'delete':
                print "del: %s %s" % (operation.db_what, 
                                      operation.db_objectId)
                print "    from:  %s %s" % (operation.db_parentObjType, operation.db_parentObjId)
                if currentOperations.has_key((operation.db_what,
                                              operation.db_objectId)):
                    del currentOperations[(operation.db_what, 
                                           operation.db_objectId)]
                else:
                    msg = "Illegal delete operation"
                    raise Exception(msg)
            elif operation.vtType == 'change':
                print "chg: %s %s %s" % (operation.db_what, 
                                         operation.db_oldObjId,
                                         operation.db_newObjId)
                print "    at:  %s %s" % (operation.db_parentObjType, operation.db_parentObjId)
                if currentOperations.has_key((operation.db_what,
                                              operation.db_oldObjId)):
                    del currentOperations[(operation.db_what, 
                                           operation.db_oldObjId)]
                else:
                    msg = "Illegal change operation"
                    raise Exception(msg)

                currentOperations[(operation.db_what, 
                                   operation.db_newObjId)] = operation
            else:
                msg = "Unrecognized operation '%s'" % operation.vtType
                raise Exception(msg)

    return currentOperations

def getCurrentOperations(actions):
    # sort the values left in the hash and return the list
    sortedOperations = getCurrentOperationDict(actions).values()
    sortedOperations.sort(lambda x, y: cmp(x.db_id, y.db_id))
    return sortedOperations

def performAction(action, workflow):
    if action.actionType == 'add':
        for operation in action.db_operations:
            workflow.db_add_object(operation.db_data, 
                                   operation.db_parentObjType,
                                   operation.db_parentObjId)
    elif action.actionType == 'change':
        for operation in action.db_operations:
            workflow.db_change_object(operation.db_data,
                                      operation.db_parentObjType,
                                      operation.db_parentObjId)
    elif action.actionType == 'delete':
        for operation in action.operations:
            workflow.db_delete_object(operation.db_objectId,
                                      operation.db_what,
                                      operation.db_parentObjType,
                                      operation.db_parentObjId)
    else:
        msg = "Unrecognized action type '%s'" % action.db_actionType
        raise Exception(msg)

def performDeletes(deleteOps, workflow):
    for operation in deleteOps:
        workflow.db_delete_object(getOldObjId(operation), operation.db_what,
                                  operation.db_parentObjType,
                                  operation.db_parentObjId)

def performAdds(addOps, workflow):
    for operation in addOps:
#         print "operation %d: %s %s" % (operation.db_id, operation.vtType,
#                                        operation.db_what)
#         print "    to:  %s %s" % (operation.db_parentObjType, operation.db_parentObjId)
        workflow.db_add_object(operation.db_data,
                               operation.db_parentObjType,
                               operation.db_parentObjId)

def performActions(actions, workflow):
    # get the current actions and run addObject on the workflow
    # note that delete actions have been removed and
    # a change after an add is effectively an add if the add is discarded
    performAdds(getCurrentOperations(actions), workflow)

################################################################################
# Analogy methods

def find_data(what, id, op_dict):
    if op_dict.has_key((what, id)):
        return op_dict[(what, id)].db_data
    else:
        msg = 'cannot find data (%s, %s)'  % (what, id)
        raise Exception(msg)
    return None

def invertOperations(op_dict, adds, deletes):
    inverse_ops = []                                
    deletes.reverse()
    for op in deletes:
        data = copy.copy(find_data(op.db_what, getOldObjId(op), op_dict))
        inv_op = DBAdd(id=-1,
                       what=op.db_what,
                       objectId=getOldObjId(op),
                       parentObjId=op.db_parentObjId,
                       parentObjType=op.db_parentObjType,
                       data=data
                       )
        inverse_ops.append(inv_op)
    adds.reverse()
    for op in adds:
        inv_op = DBDelete(id=-1,
                          what=op.db_what,
                          objectId=getNewObjId(op),
                          parentObjId=op.db_parentObjId,
                          parentObjType=op.db_parentObjType,
                          )
        inverse_ops.append(inv_op)
    return inverse_ops

def normalOperations(adds, deletes):
    new_ops = []
    for op in deletes:
        new_op = DBDelete(id=-1,
                          what=op.db_what,
                          objectId=getOldObjId(op),
                          parentObjId=op.db_parentObjId,
                          parentObjType=op.db_parentObjType,
                          )
        new_ops.append(new_op)
    for op in adds:
        new_op = DBAdd(id=-1,
                       what=op.db_what,
                       objectId=getNewObjId(op),
                       parentObjId=op.db_parentObjId,
                       parentObjType=op.db_parentObjType,
                       data=copy.copy(op.db_data))
        new_ops.append(new_op)
    return new_ops        

def simplifyOps(ops):
    addDict = {}
    deleteDict = {}
    opCount = -1
    for op in ops:
        op.db_id = opCount
        if op.vtType == 'add':
            addDict[(op.db_what, op.db_objectId)] = op
        elif op.vtType == 'delete':
            if addDict.has_key((op.db_what, op.db_objectId)):
                del addDict[(op.db_what, op.db_objectId)]
            else:
                deleteDict[(op.db_what, op.db_objectId)] = op
        elif op.vtType == 'change':
            if addDict.has_key((op.db_what, op.db_oldObjId)):
                old_old_id = getOldObjId(addDict[(op.db_what, op.db_oldObjId)])
                del addDict[(op.db_what, op.db_oldObjId)]
                addDict[(op.db_what, op.db_newObjId)] = \
                    DBChange(id=opCount,
                             what=op.db_what,
                             oldObjId=old_old_id,
                             newObjId=op.db_newObjId,
                             parentObjId=op.db_parentObjId,
                             parentObjType=op.db_parentObjType,
                             )
            else:
                addDict[(op.db_what, op.db_newObjId)] = op
        opCount -= 1

    deletes = deleteDict.values()
    deletes.sort(lambda x, y: -cmp(x.db_id, y.db_id))
    adds = addDict.values()
    adds.sort(lambda x, y: -cmp(x.db_id, y.db_id))
    return deletes + adds

def getPathAsAction(vistrail, v1, v2):
    sharedRoot = getSharedRoot(vistrail, [v1, v2])
    sharedActionChain = getActionChain(vistrail, sharedRoot)
    sharedOperationDict = getCurrentOperationDict(sharedActionChain)
    v1Actions = getActionChain(vistrail, v1, sharedRoot)
    v2Actions = getActionChain(vistrail, v2, sharedRoot)
    (v1AddDict, v1DeleteDict) = getOperationDiff(v1Actions, 
                                                 sharedOperationDict)
    (v2AddDict, v2DeleteDict) = getOperationDiff(v2Actions,
                                                 sharedOperationDict)
    
    # need to invert one of them (v1)
    v1Adds = v1AddDict.values()
    v1Adds.sort(lambda x, y: cmp(x.db_id, y.db_id))
    v1Deletes = v1DeleteDict.values()
    v1Deletes.sort(lambda x, y: cmp(x.db_id, y.db_id))
    v1InverseOps = invertOperations(sharedOperationDict, v1Adds, v1Deletes)
    
    # need to normalize ops of the other (v2)
    v2Adds = v2AddDict.values()
    v2Adds.sort(lambda x, y: cmp(x.db_id, y.db_id))
    v2Deletes = v2DeleteDict.values()
    v2Deletes.sort(lambda x, y: cmp(x.db_id, y.db_id))
    v2Ops = normalOperations(v2Adds, v2Deletes)

    allOps = v1InverseOps + v2Ops
    simplifiedOps = simplifyOps(allOps)
    return DBAction(id=-1, 
                    operations=simplifiedOps,
                    )

def addAndFixActions(startDict, actions):
    curDict = copy.copy(startDict)
    # print curDict
    for action in actions:
        print "fixing action:", action.db_id
        new_ops = []
        for op in action.db_operations:
            print "op:", op.vtType, op.db_what, getOldObjId(op)
            print "   ", op.db_parentObjType, op.db_parentObjId
            if op.vtType == 'add':
                if op.db_parentObjId is None or \
                        curDict.has_key((op.db_parentObjType, 
                                         op.db_parentObjId)):
                    curDict[(op.db_what, op.db_objectId)] = op
                    new_ops.append(op)                    
            elif op.vtType == 'change':
                if curDict.has_key((op.db_what, op.db_oldObjId)) and \
                        (op.db_parentObjId is None or \
                             curDict.has_key((op.db_parentObjType, 
                                              op.db_parentObjId))):
                    del curDict[(op.db_what, op.db_oldObjId)]
                    curDict[(op.db_what, op.db_newObjId)] = op
                    new_ops.append(op)
            elif op.vtType == 'delete':
                if (op.db_parentObjId is None or
                    curDict.has_key((op.db_parentObjType, 
                                     op.db_parentObjId))) and \
                    curDict.has_key((op.db_what, op.db_objectId)):
                    del curDict[(op.db_what, op.db_objectId)]
                    new_ops.append(op)
        action.db_operations = new_ops
    return curDict

def fixActions(vistrail, v, actions):
    startingChain = getActionChain(vistrail, v)
    startingDict = getCurrentOperationDict(startingChain)
    addAndFixActions(startingDict, actions)
    
################################################################################
# Diff methods

def getSharedRoot(vistrail, versions):
    # base case is 0
    current = copy.copy(versions)
    while 0 not in current:
        maxId = max(current)
        if current.count(maxId) == len(current):
            return maxId
        else:
            newId = vistrail.db_get_action(maxId).db_prevId
            for i, v in enumerate(current):
                if v == maxId:
                    current[i] = newId
    return 0

def getOperationDiff(actions, operationDict):
    addDict = {}
    deleteDict = {}
    for action in actions:
#         print 'action: %d' % action.db_id
        for operation in action.db_operations:
            if operation.vtType == 'add':
#                 print "add: %s %s" % (operation.db_what, 
#                                       operation.db_objectId)
                addDict[(operation.db_what, 
                         operation.db_objectId)] = operation
            elif operation.vtType == 'delete':
#                 print "del: %s %s" % (operation.db_what, 
#                                       operation.db_objectId)
                if operationDict.has_key((operation.db_what,
                                          operation.db_objectId)):
                    deleteDict[(operation.db_what,
                                operation.db_objectId)] = operation
#                     del operationDict[(operation.db_what, 
#                                        operation.db_objectId)]
                elif addDict.has_key((operation.db_what,
                                      operation.db_objectId)):
                    del addDict[(operation.db_what,
                                 operation.db_objectId)]
                else:
                    pass
            elif operation.vtType == 'change':
#                 print "chg: %s %s %s" % (operation.db_what, 
#                                          operation.db_oldObjId,
#                                          operation.db_newObjId)
                if operationDict.has_key((operation.db_what,
                                          operation.db_oldObjId)):
                    deleteDict[(operation.db_what,
                                operation.db_oldObjId)] = operation
#                     del operationDict[(operation.db_what, 
#                                        operation.db_oldObjId)]
                elif addDict.has_key((operation.db_what,
                                      operation.db_oldObjId)):
                    del addDict[(operation.db_what, operation.db_oldObjId)]

                addDict[(operation.db_what,
                         operation.db_newObjId)] = operation
            else:
                msg = "Unrecognized operation '%s'" % operation.vtType
                raise Exception(msg)

    return (addDict, deleteDict)

def updateOperationDict(operationDict, deleteOps, addOps):
    for operation in deleteOps:
        if operationDict.has_key((operation.db_what, getOldObjId(operation))):
            del operationDict[(operation.db_what, getOldObjId(operation))]
        else:
            msg = "Illegal operation: " + operation
    for operation in addOps:
        operationDict[(operation.db_what, getNewObjId(operation))] = operation
    return operationDict

def getObjects(actions):
    objects = {}
    for action in actions:
        for operation in action.db_operations:
            if not objects.has_key(operation.db_what):
                objects[operation.db_what] = []
            object = copy.copy(operation.db_data)
            objects[operation.db_what].append(object)
    return objects

def getVersionDifferences(vistrail, versions):
    sharedRoot = getSharedRoot(vistrail, versions)
    sharedActionChain = getActionChain(vistrail, sharedRoot)
    sharedOperationDict = getCurrentOperationDict(sharedActionChain)

    vOnlySorted = []
    for v in versions:
        vActions = getActionChain(vistrail, v, sharedRoot)
        (vAddDict, vDeleteDict) = getOperationDiff(vActions, 
                                                   sharedOperationDict)
        vOnlyAdds = vAddDict.values()
        vOnlyAdds.sort(lambda x,y: cmp(x.db_id, y.db_id))
        vOnlyDeletes = vDeleteDict.values()
        vOnlyDeletes.sort(lambda x,y: cmp(x.db_id, y.db_id))
        vOpDict = copy.copy(sharedOperationDict)
        updateOperationDict(vOpDict, vOnlyDeletes, vOnlyAdds)
        vOps = vOpDict.values()
        vOps.sort(lambda x,y: cmp(x.db_id, y.db_id))
        vOnlySorted.append((vOnlyAdds, vOnlyDeletes, vOps))

    sharedOps = sharedOperationDict.values()
    sharedOps.sort(lambda x, y: cmp(x.db_id, y.db_id))

    return (sharedOps, vOnlySorted)

def heuristicModuleMatch(m1, m2):
    """takes two modules and returns 1 if exact match,
    0 if function names match, -1 if no match
    
    """
    if m1.db_name == m2.db_name:
        m1_functions = copy.copy(m1.db_get_functions())
        m2_functions = copy.copy(m2.db_get_functions())
        if len(m1_functions) != len(m2_functions):
            return 0
        for f1 in m1_functions[:]:
            match = None
            for f2 in m2_functions:
                isMatch = heuristicFunctionMatch(f1, f2)
                if isMatch == 1:
                    match = f2
                    break
                elif isMatch == 0:
                    match = f2
            if match is not None:
                m1_functions.remove(f1)
                m2_functions.remove(f2)
            else:
                return 0
        if len(m1_functions) == len(m2_functions) == 0:
            return 1
        else:
            return 0
    return -1

def heuristicFunctionMatch(f1, f2):
    """takes two functions and returns 1 if exact match,
    0 if function names match, -1 if no match

    """
    if f1.db_name == f2.db_name:
        f1_parameters = copy.copy(f1.db_get_parameters())
        f2_parameters = copy.copy(f2.db_get_parameters())
        if len(f1_parameters) == len(f2_parameters):
            return 0
        for p1 in f1_parameters[:]:
            match = None
            for p2 in f2_parameters:
                isMatch = heuristicParmaterMatch(p1, p2)
                if isMatch == 1:
                    match = p2
                    break
                elif isMatch == 0:
                    match = p2
            if match is not None:
                f1_parameters.remove(p1)
                f2_parmaeters.remove(match)
            else:
                return 0
        if len(f1_parameters) == len(f2_parameters) == 0:
            return 1
        else:
            return 0
    return -1

def heurisitcParameterMatch(p1, p2):
    """takes two parameters and returns 1 if exact match,
    0 if partial match (currently undefined), -1 if no match

    """
    if p1.db_type == p2.db_type and p1.db_val == p2.db_val:
        return 1
    return -1

def heuristicConnectionMatch(c1, c2):
    c1_ports = copy.copy(c1.db_get_ports())
    c2_ports = copy.copy(c2.db_get_ports())
    for p1 in c1_ports[:]:
        match = None
        for p2 in c2_ports:
            isMatch = heuristicPortMatch(p1, p2)
            if isMatch == 1:
                match = p2
                break
            elif isMatch == 0:
                match = p2
        if match is not None:
            c1_ports.remove(p1)
            c2_ports.remove(match)
        else:
            return -1
    if len(c1_ports) == len(c2_ports) == 0:
        return 1
    return -1

def heuristicPortMatch(p1, p2):
    if p1.db_moduleId == p2.db_moduleId:
        return 1
    elif p1.db_type == p2.db_type and \
            p1.db_moduleName == p2.db_moduleName and \
            p1.db_sig == p2.db_sig:
        return 0
    return -1

def function_sig(function):
    return (function.db_name,
            [(param.db_type, param.db_val)
             for param in function.db_get_parameters()])

def getParamChanges(m1, m2, heuristic_match):
    paramChanges = []
    # need to check to see if any children of m1 and m2 are affected
    m1_functions = m1.db_get_functions()
    m2_functions = m2.db_get_functions()
    m1_unmatched = []
    m2_unmatched = []
    for f1 in m1_functions:
        # see if m2 has f1, too
        f2 = m2.db_get_function(f1.db_id)
        if f2 is None:            
            m1_unmatched.append(f1)
        else:
            # function is same, parameters have changed
            paramChanges.append((function_sig(f1), function_sig(f2)))
#             functionMatch = True
#             f1_params = f1.db_get_parameters()
#             f2_params = f2.db_get_parameters()
#             for p1 in f1_params:
#                 if f2.db_get_parameter(p1.db_id) is None:
#                     functionMatch = False
#                     m1_unmatched.append(f1)
#                     break
#             for p2 in f2_params:
#                 if f1.db_get_parameter(p2.db_id) is None:
#                     functionMatch = False
#                     m2_unmatched.append(f2)
#                     break
#             if functionMatch:


    for f2 in m2_functions:
        # see if m1 has f2, too
        if m1.db_get_function(f2.db_id) is None:
            m2_unmatched.append(f2)

    if len(m1_unmatched) + len(m2_unmatched) > 0:
        if heuristic_match and len(m1_unmatched) > 0 and len(m2_unmatched) > 0:
            # do heuristic matches
            for f1 in m1_unmatched[:]:
                matched = False
                for f2 in m2_unmatched:
                    matchValue = heuristicFunctionMatch(f1, f2)
                    if matchValue == 1:
                        # best match so quit
                        matched = f1
                        break
                    elif matchValue == 0:
                        # match, but not exact so continue to look
                        matched = f1
                if matched:
                    paramChanges.append((function_sig(f1), function_sig(f2)))
                    m1_unmatched.remove(f1)
                    m2_unmatched.remove(f2)

        for f in m1_unmatched:
            paramChanges.append((function_sig(f), (None, None)))
        for f in m2_unmatched:
            paramChanges.append(((None, None), function_sig(f)))
        
    return paramChanges

def getOldObjId(operation):
    if operation.vtType == 'change':
        return operation.db_oldObjId
    return operation.db_objectId

def getNewObjId(operation):
    if operation.vtType == 'change':
        return operation.db_newObjId
    return operation.db_objectId

def setOldObjId(operation, id):
    if operation.vtType == 'change':
        operation.db_oldObjId = id
    else:
        operation.db_objectId = id

def setNewObjId(operation, id):
    if operation.vtType == 'change':
        operation.db_newObjId = id
    else:
        operation.db_objectId = id

def getWorkflowDiff(vistrail, v1, v2, heuristic_match=True):
    (sharedOps, vOnlyOps) = \
        getVersionDifferences(vistrail, [v1, v2])

    sharedWorkflow = DBWorkflow()
    performAdds(sharedOps, sharedWorkflow)

    # FIXME better to do additional ops (and do deletes) or do this?
    v1Workflow = DBWorkflow()
    v1Ops = vOnlyOps[0][2]
    performAdds(v1Ops, v1Workflow)

    v2Workflow = DBWorkflow()
    v2Ops = vOnlyOps[1][2]
    performAdds(v2Ops, v2Workflow)

    # FIXME connections do not check their ports
    sharedModuleIds = []
    sharedConnectionIds = []
    sharedFunctionIds = {}
    for op in sharedOps:
        if op.what == 'module':
            sharedModuleIds.append(getNewObjId(op))
        elif op.what == 'connection':
            sharedConnectionIds.append(getNewObjId(op))
        elif op.what == 'function':
            sharedFunctionIds[getNewObjId(op)] = op.db_parentObjId
    
    vOnlyModules = []
    vOnlyConnections = []
    paramChgModules = {}
    for (vAdds, vDeletes, _) in vOnlyOps:
        moduleDeleteIds = []
        connectionDeleteIds = []
        for op in vDeletes:
            if op.what == 'module':
                moduleDeleteIds.append(getOldObjId(op))
                if getOldObjId(op) in sharedModuleIds:
                    sharedModuleIds.remove(getOldObjId(op))
                if paramChgModules.has_key(getOldObjId(op)):
                    del paramChgModules[getOldObjId(op)]
            elif op.what == 'function' and op.db_parentObjType == 'module' \
                    and op.db_parentObjId in sharedModuleIds:
                # have a function change
                paramChgModules[op.db_parentObjId] = None
                sharedModuleIds.remove(op.db_parentObjId)
            elif op.what == 'parameter' and op.db_parentObjType == 'function' \
                    and sharedFunctionIds.has_key(op.db_parentObjId):
                # have a parameter change
                moduleId = sharedFunctionIds[op.db_parentObjId]
                if moduleId in sharedModuleIds:
                    paramChgModules[moduleId] = None
                    sharedModuleIds.remove(moduleId)
            elif op.what == 'connection':
                connectionDeleteIds.append(getOldObjId(op))
                if getOldObjId(op) in sharedConnectionIds:
                    sharedConnectionIds.remove(getOldObjId(op))

        moduleAddIds = []
        connectionAddIds = []
        for op in vAdds:
            if op.what == 'module':
                moduleAddIds.append(getNewObjId(op))
            elif op.what == 'function' and op.db_parentObjType == 'module' \
                    and op.db_parentObjId in sharedModuleIds:
                # have a function change
                paramChgModules[op.db_parentObjId] = None
                sharedModuleIds.remove(op.db_parentObjId)
            elif op.what == 'parameter' and op.db_parentObjType == 'function' \
                    and sharedFunctionIds.has_key(op.db_parentObjId):
                # have a parameter change
                moduleId = sharedFunctionIds[op.db_parentObjId]
                if moduleId in sharedModuleIds:
                    paramChgModules[moduleId] = None
                    sharedModuleIds.remove(moduleId)
            elif op.what == 'connection':
                connectionAddIds.append(getOldObjId(op))

        vOnlyModules.append((moduleAddIds, moduleDeleteIds))
        vOnlyConnections.append((connectionAddIds, connectionDeleteIds))

    sharedModulePairs = [(id, id) for id in sharedModuleIds]
    v1Only = vOnlyModules[0][0]
    v2Only = vOnlyModules[1][0]
    for id in vOnlyModules[1][1]:
        if id not in vOnlyModules[0][1]:
            v1Only.append(id)
    for id in vOnlyModules[0][1]:
        if id not in vOnlyModules[1][1]:
            v2Only.append(id)

    sharedConnectionPairs = [(id, id) for id in sharedConnectionIds]
    c1Only = vOnlyConnections[0][0]
    c2Only = vOnlyConnections[1][0]
    for id in vOnlyConnections[1][1]:
        if id not in vOnlyConnections[0][1]:
            c1Only.append(id)
    for id in vOnlyConnections[0][1]:
        if id not in vOnlyConnections[1][1]:
            c2Only.append(id)

    paramChgModulePairs = [(id, id) for id in paramChgModules.keys()]

    # add heuristic matches
    if heuristic_match:
        # match modules
        for (m1_id, m2_id) in paramChgModulePairs[:]:
            m1 = v1Workflow.db_get_module(m1_id)
            m2 = v2Workflow.db_get_module(m2_id)
            if heuristicModuleMatch(m1, m2) == 1:
                paramChgModulePairs.remove((m1_id, m2_id))
                sharedModulePairs.append((m1_id, m2_id))

        for m1_id in v1Only[:]:
            m1 = v1Workflow.db_get_module(m1_id)
            match = None
            for m2_id in v2Only:
                m2 = v2Workflow.db_get_module(m2_id)
                isMatch = heuristicModuleMatch(m1, m2)
                if isMatch == 1:
                    match = (m1_id, m2_id)
                    break
                elif isMatch == 0:
                    match = (m1_id, m2_id)
            if match is not None:
                if isMatch == 1:
                    v1Only.remove(match[0])
                    v2Only.remove(match[1])
                    sharedModulePairs.append(match)
                else:
                    v1Only.remove(match[0])
                    v2Only.remove(match[1])
                    paramChgModulePairs.append(match)

        # match connections
        for c1_id in c1Only[:]:
            c1 = v1Workflow.db_get_connection(c1_id)
            match = None
            for c2_id in c2Only:
                c2 = v2Workflow.db_get_connection(c2_id)
                isMatch = heuristicConnectionMatch(c1, c2)
                if isMatch == 1:
                    match = (c1_id, c2_id)
                    break
                elif isMatch == 0:
                    match = (c1_id, c2_id)
            if match is not None:
                # don't have port changes yet
                c1Only.remove(match[0])
                c2Only.remove(match[1])
                sharedConnectionPairs.append(match)
                    
    paramChanges = []
    #     print sharedModulePairs
    #     print paramChgModulePairs
    for (m1_id, m2_id) in paramChgModulePairs:
        m1 = v1Workflow.db_get_module(m1_id)
        m2 = v2Workflow.db_get_module(m2_id)
        paramChanges.append(((m1_id, m2_id),
                             getParamChanges(m1, m2, heuristic_match)))

    return (v1Workflow, v2Workflow, 
            sharedModulePairs, v1Only, v2Only, paramChanges,
            sharedConnectionPairs, c1Only, c2Only)