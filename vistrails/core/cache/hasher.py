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
"""Hasher class for vistrail items."""

from core.cache.utils import hash_list
import sha

##############################################################################

class Hasher(object):

    @staticmethod
    def parameter_signature(p):
        hasher = sha.new()
        hasher.update(p.type)
        hasher.update(p.strValue)
        hasher.update(p.name)
        return hasher.digest()

    @staticmethod
    def function_signature(function):
        return hash_list(function.params, Hasher.parameter_signature)

    @staticmethod
    def connection_signature(c):
        hasher = sha.new()
        hasher.update(c.source.name)
        hasher.update(c.destination.name)
        return hasher.digest()

    @staticmethod
    def module_signature(obj):
        hasher = sha.new()
        hasher.update(obj.name)
        hasher.update(hash_list(obj.functions, Hasher.function_signature))
        return hasher.digest()

    @staticmethod
    def subpipeline_signature(module_sig, upstream_sigs):
        """Returns the signature for a subpipeline, given the
signatures for the upstream pipelines and connections.

        WARNING: For efficiency, upstream_sigs is mutated!
        """
        hasher = sha.new()
        hasher.update(module_sig)
        upstream_sigs.sort()
        for pipeline_connection_sig in upstream_sigs:
            hasher.update(pipeline_connection_sig)
        return hasher.digest()