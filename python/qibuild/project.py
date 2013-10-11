import os
import re
import sys
import platform

from qisys import ui
import qisys.command
import qisys.sh
import qibuild.cmake
import qibuild.build
import qibuild.gdb
import qibuild.dylibs
import qibuild.dlls
import qitoolchain.toolchain

class BuildProject(object):
    def __init__(self, build_worktree, worktree_project):
        self.build_worktree = build_worktree
        self.build_config = build_worktree.build_config
        self.path = worktree_project.path
        self.src = worktree_project.src
        self.name = None
        # depends is a set at this point because they are not sorted yet
        self.build_depends = set()
        self.run_depends = set()
        self.test_depends = set()

    @property
    def qiproject_xml(self):
        """ Path to qiproject.xml """
        return os.path.join(self.path, "qiproject.xml")

    @property
    def cmake_qibuild_dir(self):
        return qibuild.cmake.get_cmake_qibuild_dir()

    @property
    def build_directory(self):
        """ Return a suitable build directory, depending on the
        build setting of the worktree: the name of the toolchain,
        the build profiles, and the build type (debug/release)

        """
        parts = ["build"]
        toolchain = self.build_config.toolchain
        build_type = self.build_config.build_type
        visual_studio = self.build_config.using_visual_studio
        if toolchain:
            parts.append(toolchain.name)
        else:
            parts.append("sys-%s-%s" % (platform.system().lower(),
                                        platform.machine().lower()))
        profiles = self.build_config.profiles
        for profile in profiles:
            parts.append(profile)

        # When using cmake + visual studio, sharing the same build dir with
        # several build config is mandatory.
        # Otherwise, it's not a good idea, so we always specify it
        # when it's not "Debug" (the default)
        if not visual_studio:
            if build_type and build_type != "Debug":
                parts.append(build_type.lower())

        # FIXME: handle custom build dir
        return os.path.join(self.path, "-".join(parts))

    @property
    def cmake_cache(self):
        return os.path.join(self.build_directory, "CMakeCache.txt")

    @property
    def cmake_args(self):
        """ The list of CMake arguments to use when configuring the
        project.
        Delegates to build_config.cmake_args

        """
        return self.build_config.cmake_args

    @property
    def build_env(self):
        """ The environment to use when calling cmake or build commands

        """
        return self.build_config.build_env

    @property
    def sdk_directory(self):
        """ The sdk directory in the build directory """
        # TODO: handle unique sdk dir?
        return os.path.join(self.build_directory, "sdk")

    @property
    def cmake_generator(self):
        return self.build_config.cmake_generator

    @property
    def using_visual_studio(self):
        return self.build_config.using_visual_studio
    @property
    def using_make(self):
        return self.build_config.using_make

    def write_qi_path_conf(self, sdk_dirs):
        """ Write the <build>/sdk/share/qi/path.conf file. This file
        can be used for instance by qi::path::find() functions, to
        find files from the dependencies' build directory

        """
        to_write = "# File autogenerated by qibuild configure based on\n"
        to_write += "# dependencies found in qiproject.xml\n"
        to_write += "\n"

        for sdk_dir in sdk_dirs:
            to_write += qisys.sh.to_posix_path(sdk_dir) + "\n"

        path_dconf = os.path.join(self.sdk_directory, "share", "qi")
        qisys.sh.mkdir(path_dconf, recursive=True)

        path_conf = os.path.join(path_dconf, "path.conf")
        with open(path_conf, "w") as fp:
            fp.write(to_write)

    def write_dependencies_cmake(self, sdk_dirs):
        """ Write the dependencies.cmake file. This will be read by
        qibuild-config.cmake to set CMAKE_FIND_ROOT_PATH and
        qibuild_DIR, so that just running `cmake ..` works

        """
        to_write = """
#############################################
#QIBUILD AUTOGENERATED FILE. DO NOT EDIT.
#############################################

# Add path to CMake framework path if necessary:
set(_qibuild_path "{cmake_qibuild_dir}")
list(FIND CMAKE_MODULE_PATH "${{_qibuild_path}}" _found)
if(_found STREQUAL "-1")
  # Prefer cmake files matching  current qibuild installation
  # over cmake files in the cross-toolchain
  list(INSERT CMAKE_MODULE_PATH 0 "${{_qibuild_path}}")


  # Uncomment this if you really need to use qibuild
  # cmake files from the cross-toolchain
  # list(APPEND CMAKE_MODULE_PATH "${{_qibuild_path}}")
endif()

# Dependencies:
{dep_to_add}

# Store CMAKE_MODULE_PATH and CMAKE_FIND_ROOT_PATH in cache:
set(CMAKE_MODULE_PATH ${{CMAKE_MODULE_PATH}} CACHE INTERNAL ""  FORCE)
set(CMAKE_FIND_ROOT_PATH ${{CMAKE_FIND_ROOT_PATH}} CACHE INTERNAL ""  FORCE)

{custom_cmake_code}
"""
        custom_cmake_code = ""
        if self.build_config.local_cmake:
            to_include = qisys.sh.to_posix_path(self.build_config.local_cmake)
            custom_cmake_code += 'include("%s")\n' % to_include

        cmake_qibuild_dir = self.cmake_qibuild_dir
        cmake_qibuild_dir = qisys.sh.to_posix_path(cmake_qibuild_dir)
        dep_to_add = ""
        for sdk_dir in sdk_dirs:

            dep_to_add += """
    list(FIND CMAKE_FIND_ROOT_PATH "{sdk_dir}" _found)
    if(_found STREQUAL "-1")
        list(INSERT CMAKE_FIND_ROOT_PATH 0 "{sdk_dir}")
    endif()
    """.format(sdk_dir=qisys.sh.to_posix_path(sdk_dir))

        to_write = to_write.format(
            cmake_qibuild_dir=cmake_qibuild_dir,
            dep_to_add=dep_to_add,
            custom_cmake_code=custom_cmake_code
        )

        import qibuild
        qibuild_python = os.path.join(qibuild.__file__, "..", "..")
        qibuild_python = os.path.abspath(qibuild_python)
        qibuild_python = qisys.sh.to_posix_path(qibuild_python)
        to_write += """
set(QIBUILD_PYTHON_PATH "%s" CACHE STRING "" FORCE)
""" % qibuild_python


        qisys.sh.mkdir(self.build_directory, recursive=True)
        dep_cmake = os.path.join(self.build_directory, "dependencies.cmake")
        qisys.sh.write_file_if_different(to_write, dep_cmake)

    def configure(self, **kwargs):
        """ Delegate to :py:func:`qibuild.cmake.cmake` """
        qisys.sh.mkdir(self.build_directory, recursive=True)
        cmake_args = self.cmake_args
        # only required the first time, afterwards this setting is
        # written in the cache by dependencies.cmake
        cmake_qibuild_dir = self.cmake_qibuild_dir
        cmake_qibuild_dir = os.path.join(cmake_qibuild_dir, "qibuild")
        cmake_qibuild_dir = qisys.sh.to_posix_path(cmake_qibuild_dir)
        cmake_args.append("-Dqibuild_DIR=%s" % cmake_qibuild_dir)
        try:
            qibuild.cmake.cmake(self.path, self.build_directory,
                                cmake_args, env=self.build_env, **kwargs)
        except qisys.command.CommandFailedException:
            raise qibuild.build.ConfigureFailed(self)

    def build(self, num_jobs=None, rebuild=False, target=None,
              verbose_make=False, coverity=False, env=None):
        """ Build the project """
        timer = ui.timer("make %s" % self.name)
        timer.start()
        build_type = self.build_config.build_type

        cmd = []
        if coverity:
            if not qisys.command.find_program("cov-build"):
                raise Exception("cov-build was not found on the system")
            cov_dir = os.path.join(self.build_directory, "coverity")
            qisys.sh.mkdir(cov_dir)
            cmd += ["cov-build", "--dir", cov_dir]

        cmd += ["cmake", "--build", self.build_directory,
                         "--config", build_type]

        if target:
            cmd += ["--target", target]

        if rebuild:
            cmd += ["--clean-first"]
        cmd += [ "--" ]
        cmd += self.parse_num_jobs(self.build_config.num_jobs)

        if not env:
            build_env = self.build_env.copy()
        else:
            build_env = env
        if verbose_make:
            if "Makefiles" in self.cmake_generator:
                build_env["VERBOSE"] = "1"
            if self.cmake_generator == "Ninja":
                cmd.append("-v")
        try:
            qisys.command.call(cmd, env=build_env)
        except qisys.command.CommandFailedException:
            raise qibuild.build.BuildFailed(self)

        timer.stop()

    def parse_num_jobs(self, num_jobs, cmake_generator=None):
        """ Convert a number of jobs to a list of cmake args """
        if not cmake_generator:
            cmake_generator = \
                    qibuild.cmake.get_cached_var(self.build_directory, "CMAKE_GENERATOR")
        if num_jobs is None:
            return list()
        if "Unix Makefiles" in cmake_generator or \
            "Ninja" in cmake_generator:
            return ["-j", str(num_jobs)]
        if cmake_generator == "NMake Makefiles":
            mess   = "-j is not supported for %s\n" % cmake_generator
            mess += "On Windows, you can use Jom or Ninja instead to compile "
            mess += "with multiple processors"
            raise Exception(mess)
        if "Visual Studio" in cmake_generator or \
            cmake_generator == "Xcode" or \
            "JOM" in cmake_generator:
            ui.warning("-j is ignored when used with", cmake_generator)
            return list()
        ui.warning("Unknown generator: %s, ignoring -j option" % cmake_generator)
        return list()


    def install(self, destdir, prefix="/", components=None, num_jobs=1,
                split_debug=False):
        """ Install the project

        :param project: project name.
        :param destdir: destination. Note that when using `qibuild install`,
          we will first call `cmake` to make sure `CMAKE_INSTALL_PREFIX` is
          ``/``. But this function simply calls ``cmake --target install``
          in the simple case.
        :param runtime: Whether to install the project as a runtime
           package or not.
           (see :ref:`cmake-install` section for the details)
        :package split_debug: split the debug symbols out of the binaries
            useful for `qibuild deploy`

        """
        # DESTDIR=/tmp/foo and CMAKE_PREFIX="/usr/local" means
        # dest = /tmp/foo/usr/local
        destdir = qisys.sh.to_native_path(destdir)
        build_env = self.build_env.copy()
        build_env["DESTDIR"] = destdir
        # Must make sure prefix is not seen as an absolute path here:
        dest = os.path.join(destdir, prefix[1:])
        dest = qisys.sh.to_native_path(dest)

        cprefix = qibuild.cmake.get_cached_var(self.build_directory,
                                               "CMAKE_INSTALL_PREFIX")
        if cprefix != prefix:
            qibuild.cmake.cmake(self.path, self.build_directory,
                ['-DCMAKE_INSTALL_PREFIX=%s' % prefix],
                clean_first=False,
                env=build_env)
        else:
            mess = "Skipping configuration of project %s\n" % self.name
            mess += "CMAKE_INSTALL_PREFIX is already correct"
            ui.debug(mess)

        # Hack for http://www.cmake.org/Bug/print_bug_page.php?bug_id=13934
        if self.using_make:
            self.build(target="preinstall", num_jobs=num_jobs, env=build_env)
        if components:
            for component in components:
                self._install_component(destdir, component)
        else:
            self.build(target="install", env=build_env)

        if split_debug:
            self.split_debug(destdir)

    def _install_component(self, destdir, component):
        build_env = self.build_env.copy()
        build_env["DESTDIR"] = destdir

        cmake_args = list()
        cmake_args += ["-DBUILD_TYPE=%s" % self.build_config.build_type]
        cmake_args += ["-DCOMPONENT=%s" % component]
        cmake_args += ["-P", "cmake_install.cmake", "--"]
        ui.debug("Installing", component)
        qisys.command.call(["cmake"] + cmake_args, cwd=self.build_directory,
                            env=build_env)

    def deploy(self, url, port=22, split_debug=False,
               use_rsync=True, with_tests=True):
        """ Deploy the project to a remote url """
        destdir = os.path.join(self.build_directory, "deploy")
        #create folder for project without install rules
        qisys.sh.mkdir(destdir, recursive=True)
        components=["runtime"]
        if with_tests:
            components.append("test")
        self.install(destdir, components=components)
        if split_debug:
            self.split_debug(destdir)
        ui.info(ui.green, "Sending binaries to target ...")
        qibuild.deploy.deploy(destdir, url, use_rsync=use_rsync, port=port)


    def fix_shared_libs(self, paths):
        """ Do some magic so that shared libraries from other projects and
        packages from toolchains are found

        Called by CMakeBuilder before building

        :param paths: a list of paths from which to look for dependencies

        """
        if sys.platform == "darwin":
            qibuild.dylibs.fix_dylibs(self.sdk_directory, paths=paths)
        if sys.platform.startswith("win"):
            mingw = self.build_config.using_mingw
            qibuild.dlls.fix_dlls(self.sdk_directory, paths=paths,
                                  mingw=mingw, env=self.build_env)


    def split_debug(self, destdir):
        """ Split debug symbols after install """
        if self.using_visual_studio:
            raise Exception("split debug not supported on Visual Studio")
        ui.info(ui.green, "Splitting debug symbols from binaries ...")
        tool_paths = dict()
        for name in ["objcopy", "objdump"]:
            tool_path = qibuild.cmake.get_binutil(name,
                                                    build_dir=self.build_directory,
                                                    env=self.build_env)
            tool_paths[name] = tool_path

        missing = [x for x in tool_paths if not tool_paths[x]]
        if missing:
            mess  = """\
Could not split debug symbols from binaries for project {name}.
The following tools were not found: {missing}\
"""
            mess = mess.format(name=self.name, missing = ", ".join(missing))
            ui.warning(mess)
            return
        qibuild.gdb.split_debug(destdir, **tool_paths)

    def get_build_dirs(self, all_configs=False):
        """Return a dictionary containing the build directory list
        for the known and the unknown configurations::

            build_directories = {
                'known_configs' = [],
                'unknown_configs' = [],
            }

        Note: if all_configs if False, then the list of the unknown
        configuration remains empty.

        """
        if not all_configs:
            bdirs = list()
            if os.path.isdir(self.build_directory):
                bdirs.append(self.build_directory)
            return {'known_configs': bdirs, 'unknown_configs': list()}

        # build directory name pattern:
        # 'build-<tc_name>[-<profile>]...[-release]'
        qibuild_xml = self.build_worktree.qibuild_xml
        profiles = qibuild.profile.parse_profiles(qibuild_xml)
        profiles = list(profiles.keys())
        profiles = [re.escape(x) for x in profiles]
        toolchains = qitoolchain.toolchain.get_tc_names()
        toolchains.append("sys-%s-%s" % (platform.system().lower(),
                                        platform.machine().lower()))
        toolchains = [re.escape(x) for x in toolchains]
        bdir_regex = r"^build"
        bdir_regex += r"(-(" + "|".join(toolchains) + "))"
        bdir_regex += r"(-(" + "|".join(profiles) + "))*"
        bdir_regex += r"(-release)?$"
        bdir_re = re.compile(bdir_regex)
        ui.debug("matching:", bdir_regex)
        dirs = os.listdir(self.path)
        ret = {'known_configs': list(), 'unknown_configs': list()}
        for bdir in dirs:
            if bdir_re.match(bdir):
                ret['known_configs'].append(bdir)
            elif bdir.startswith("build-"):
                ret['unknown_configs'].append(bdir)
        for k in ret.keys():
            ret[k] = [os.path.join(self.path, x) for x in ret[k]]
        return ret

    def __repr__(self):
        return "<BuildProject %s in %s>" % (self.name, self.src)

    def __eq__(self, other):
        return self.name == other.name and self.src == other.src

    def __ne__(self, other):
        return not (self == other)



class BadProjectConfig(Exception):
    pass
