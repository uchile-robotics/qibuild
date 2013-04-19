## Copyright (c) 2012, 2013 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

set(_cv_versions "2.3.1" "2.4.3")

function(opencv2_flib name)
  cmake_parse_arguments(ARG "" "" "DEPENDS" ${ARGN})
  string(TOUPPER ${name} _prefix)
  set(_prefix OPENCV2_${_prefix})
  set(_header opencv2/${name}/${name}.hpp)
  set(_libname opencv_${name})
  fpath(${_prefix} ${_header})
  if(UNIX)
    flib(${_prefix} ${_libname})
  else()
    set(_d_names)
    set(_o_names)
    foreach(_version ${_cv_versions})
      string(REPLACE "." "" _short_version ${_version})
      list(APPEND _d_names ${_libname}${_short_version}d)
      list(APPEND _o_names ${_libname}${_short_version})
    endforeach()
    flib(${_prefix} DEBUG     NAMES ${_d_names})
    flib(${_prefix} OPTIMIZED NAMES ${_o_names})
  endif()

  if(ARG_DEPENDS)
    set(_lib_deps)
    foreach(_dep ${ARG_DEPENDS})
      string(TOUPPER ${_dep} _U_dep)
      list(APPEND _lib_deps OPENCV2_${_U_dep})
    endforeach()
    qi_persistent_set(${_prefix}_DEPENDS ${_lib_deps})
  endif()
  export_lib(${_prefix})
endfunction()
