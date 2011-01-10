##
## Author(s):
##  - Cedric GESTES <gestes@aldebaran-robotics.com>
##
## Copyright (C) 2009, 2010 Aldebaran Robotics
##

#! QiBuild Stage
# ===============
# Cedric GESTES <gestes@aldebaran-robotics.com>
#
# This module make libraries and executables build in this projects available
# to others projects.
#

#! Generate a 'name'-config.cmake, allowing other project to find the library.
# \arg:target a target created with qi_create_lib
#
function(qi_stage_lib target)
  qi_debug("BINLIB: stage_lib (${_targetname})")
  check_is_target("${target}")

  _qi_stage_lib_sdk(${target} ${ARGN})
  _qi_stage_lib_redist(${target} ${ARGN})
endfunction()

#! stage a script
function(qi_stage_script _file _name)
  qi_warning("qi_stage_script not implemented")
endfunction()

#! stage an executable
# \arg:target the target
function(qi_stage_bin _targetname)
  qi_warning("qi_stage_bin not implemented")
endfunction()

#! stage a header only library.
#
function(qi_stage_header _name)
  qi_warning("qi_stage_header not implemented")
endfunction()
