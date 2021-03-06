## Copyright (c) 2012-2016 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

import qibuild.find
import pytest
import qisys

def test_make_host_tools(qibuild_action, fake_ctc):
    footool_proj = qibuild_action.add_test_project("footool")
    qibuild_action.add_test_project("usefootool")
    qibuild_action("make-host-tools", "usefootool")
    qibuild.find.find_bin([footool_proj.sdk_directory], "footool", expect_one=True)
    qibuild_action("configure", "usefootool", "--config", "fake-ctc")

def test_recurse_deps(qibuild_action):
    footool_proj = qibuild_action.add_test_project("footool")
    qibuild_action.add_test_project("usefootool")
    qibuild_action.create_project("bar", run_depends=["usefootool"])
    qibuild_action("make-host-tools", "bar")
    qibuild.find.find_bin([footool_proj.sdk_directory], "footool", expect_one=True)

def test_building_host_tools_in_release(qibuild_action, record_messages):
    qibuild_action.add_test_project("footool")
    qibuild_action.add_test_project("usefootool")
    record_messages.reset()
    qibuild_action("make-host-tools", "--release", "usefootool")
    assert record_messages.find("Building footool in Release")
    qibuild_action("configure", "usefootool")
    qibuild_action("make", "usefootool")

def test_no_project_specified(qibuild_action):
    qibuild_action.add_test_project("footool")
    usefootool_proj = qibuild_action.add_test_project("usefootool")
    qibuild_action.chdir(usefootool_proj.path)
    qibuild_action("make-host-tools")
    qibuild_action("configure")

def test_using_dash_all(qibuild_action):
    qibuild_action.add_test_project("footool")
    qibuild_action.add_test_project("usefootool")
    qibuild_action("make-host-tools", "--all")
    qibuild_action("configure", "usefootool")

def test_not_building_host_tool_tests(qibuild_action):
    footool_proj = qibuild_action.add_test_project("footool")
    qibuild_action.add_test_project("usefootool")
    qibuild_action("make-host-tools", "usefootool")
    qibuild_action("configure", "usefootool")
    # pylint: disable-msg=E1101
    with pytest.raises(qibuild.find.NotFound):
        qibuild.find.find_bin([footool_proj.sdk_directory], "test_footool")
