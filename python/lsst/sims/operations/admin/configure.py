import commons
from distutils.util import strtobool
import getpass
import logging
import os
import sys
import string
import shutil

from lsst.sims.operations.admin import path

# used in cmd-line tool
PREPARE = 'prepare'
DIRTREE = 'directory-tree'
ETC = 'etc'
CLIENT = 'client'

MYSQL = 'mysql'
OPSIM = 'opsim'

COMPONENTS = [MYSQL]
STEP_RUN_LIST = [DIRTREE, ETC] + COMPONENTS + [CLIENT]
STEP_LIST = [PREPARE] + STEP_RUN_LIST
STEP_DOC = {
    PREPARE: "create opsim_run_dir and attach it to current opsim instance",
    DIRTREE: "create directory tree in opsim_run_dir",
    ETC: "fill opsim_run_dir configuration files with values issued " +
         "from meta-config file $opsim_run_dir/opsim-meta.conf""",
    MYSQL: "remove MySQL previous data, install db and set password",
    CLIENT: "create client configuration file (used by integration tests "
            "for example)"
}

STEP_ABBR = dict()
for step in STEP_LIST:
    if step in COMPONENTS:
        STEP_ABBR[step] = step[0].upper()
    else:
        STEP_ABBR[step] = step[0]


def exists_and_is_writable(dir):
    """
    Test if a dir exists. If no creates it, if yes checks if it is writeable.
    Return True if a writeable directory exists at the end of function
    execution, else False
    """
    logger = logging.getLogger()
    logger.debug("Checking existence and write access for : %s", dir)
    if not os.path.exists(dir):
        try:
            os.makedirs(dir)
        except OSError:
            logger.error("Unable to create dir : %s", dir)
            return False
    elif not path.is_writable(dir):
        return False
    return True


# TODO : put in a shell script
def check_root_dirs():

    logger = logging.getLogger()

    config = commons.getConfig()

    for (section, option) in (('opsim', 'base_dir'), ('opsim', 'log_dir'),
                              ('opsim', 'tmp_dir'),
                              ('mysqld', 'data_dir')):
        dir = config[section][option]
        if not exists_and_is_writable(dir):
            logging.fatal("%s is not writable check/update permissions or"
                          " change config['%s']['%s']", dir, section, option)
            sys.exit(1)

    for suffix in ('etc', 'var', 'var/lib', 'var/run', 'var/run/mysqld',
                   'var/lock/subsys'):
        dir = os.path.join(config['opsim']['run_base_dir'], suffix)
        if not exists_and_is_writable(dir):
            logging.fatal("%s is not writable check/update permissions", dir)
            sys.exit(1)

    # user config
    user_config_dir = os.path.join(os.getenv("HOME"), ".lsst")
    if not exists_and_is_writable(user_config_dir):
        logging.fatal("%s is not writable check/update permissions", dir)
        sys.exit(1)
    logger.info("opsim directory structure creation succeeded")


def check_root_symlinks():
    """
    symlinks creation for directories externalised from opsim run dir
    i.e. OPSIMRUN_DIR/var/log will be symlinked to config['opsim']['log_dir']
    if needed
    """
    log = logging.getLogger()
    config = commons.getConfig()

    for (section, option, symlink_suffix) in (('opsim', 'log_dir', 'var/log'),
                                              ('opsim', 'tmp_dir', 'tmp'),
                                              ('mysqld', 'data_dir',
                                               'var/lib/mysql')):
        symlink_target = config[section][option]
        default_dir = os.path.join(config['opsim']['run_base_dir'],
                                   symlink_suffix)

        # A symlink is needed if the target directory is not set to its
        # default value
        if not os.path.samefile(symlink_target,
                                os.path.realpath(default_dir)):
            if os.path.exists(default_dir):
                if os.path.islink(default_dir):
                    os.unlink(default_dir)
                else:
                    log.fatal("Please remove {0} and restart the "
                              "configuration procedure".format(default_dir))
                    sys.exit(1)
            _symlink(symlink_target, default_dir)

    log.info("opsim symlinks creation for externalized directories succeeded")


def _symlink(target, link_name):
    logger = logging.getLogger()
    logger.debug("Creating symlink, target : %s, link name : %s ", target,
                 link_name)
    os.symlink(target, link_name)


def uninstall(target, source, env):
    logger = logging.getLogger()
    config = commons.getConfig()
    uninstall_paths = [os.path.join(config['opsim']['log_dir']),
                       os.path.join(config['mysqld']['data_dir']),
                       os.path.join(config['opsim']['scratch_dir']), ]
    for upath in uninstall_paths:
        if not os.path.exists(upath):
            logger.info("Not uninstalling %s because it doesn't exists.",
                        upath)
        else:
            shutil.rmtree(upath)

template_params_dict = None


def _get_template_params():
    """
    Compute templates parameters from opsim meta-configuration file from PATH
    or from environment variables for products not needed during build
    """
    logger = logging.getLogger()
    config = commons.getConfig()

    global template_params_dict

    if template_params_dict is None:

        testdata_dir = os.getenv('OPSIMTESTDATA_DIR',
                                 "NOT-AVAILABLE # please set environment "
                                 "variable OPSIMTESTDATA_DIR if needed")

        params_dict = {
            'PATH': os.environ.get('PATH'),
            'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH'),
            'OPSIM_MASTER': config['opsim']['master'],
            'OPSIM_DIR': config['opsim']['base_dir'],
            'OPSIM_RUN_DIR': config['opsim']['run_base_dir'],
            'OPSIM_UNIX_USER': getpass.getuser(),
            'OPSIM_LOG_DIR': config['opsim']['log_dir'],
            'OPSIM_META_CONFIG_FILE': config['opsim']['meta_config_file'],
            'OPSIM_PID_DIR': os.path.join(config['opsim']['run_base_dir'],
                                          "var", "run"),
            'OPSIM_USER': config['opsim']['user'],
            'OPSIM_PASS': config['opsim']['password'],
            'OPSIM_SCRATCH_DIR': config['opsim']['scratch_dir'],
            'MYSQL_DIR': config['mysqld']['base_dir'],
            'MYSQLD_DATA_DIR': config['mysqld']['data_dir'],
            'MYSQLD_PORT': config['mysqld']['port'],
            # used for mysql-proxy in mono-node
            'MYSQLD_HOST': '127.0.0.1',
            'MYSQLD_SOCK': config['mysqld']['sock'],
            'MYSQLD_USER': config['mysqld']['user'],
            'MYSQLD_PASS': config['mysqld']['password'],
            'HOME': os.path.expanduser("~"), }

        logger.debug("Template input parameters:\n {0}".format(params_dict))
        template_params_dict = params_dict
    else:
        params_dict = template_params_dict

    return params_dict


def _set_perms(file):
    (path, basename) = os.path.split(file)
    script_list = [c + ".sh" for c in COMPONENTS]
    if (os.path.basename(path) == "bin" or
            os.path.basename(path) == "init.d" or
            basename in script_list):
        os.chmod(file, 0760)
    # all other files are configuration files
    else:
        os.chmod(file, 0660)


def apply_tpl(src_file, target_file, params_dict=None):
    """
    Creating one configuration file from one template
    """

    logger = logging.getLogger()
    logger.debug("Creating {0} from {1}".format(target_file, src_file))

    if params_dict is None:
        params_dict = _get_template_params()

    with open(src_file, "r") as tpl:
        t = OpSimConfigTemplate(tpl.read())

    out_cfg = t.safe_substitute(**params_dict)
    for match in t.pattern.findall(t.template):
        name = match[1]
        if len(name) != 0 and not name in params_dict:
            logger.fatal("Template \"%s\" in file %s is not defined in "
                         "configuration tool", name, src_file)
            sys.exit(1)

    dirname = os.path.dirname(target_file)
    if not os.path.exists(dirname):
        os.makedirs(os.path.dirname(target_file))
    with open(target_file, "w") as cfg:
        cfg.write(out_cfg)


def apply_templates(template_root, dest_root):

    logger = logging.getLogger()

    logger.info("Creating configuration from templates")
    if not os.path.isdir(template_root):
        logger.fatal("Template root directory: {0} doesn't exist."
                     .format(template_root))
        sys.exit(1)

    for root, dirs, files in os.walk(template_root):
        os.path.normpath(template_root)
        suffix = root[len(template_root) + 1:]
        dest_dir = os.path.join(dest_root, suffix)
        for fname in files:
            src_file = os.path.join(root, fname)
            target_file = os.path.join(dest_dir, fname)

            apply_tpl(src_file, target_file)

            # applying perms
            _set_perms(target_file)

    return True


def user_yes_no_query(question):
    sys.stdout.write('\n%s [y/n]\n' % question)
    while True:
        try:
            return strtobool(raw_input().lower())
        except ValueError:
            sys.stdout.write('Please respond with \'y\' or \'n\'.\n')


class OpSimConfigTemplate(string.Template):
    delimiter = '{{'
    pattern = r'''
    \{\{(?:
    (?P<escaped>\{\{)|
    (?P<named>[_a-z][_a-z0-9]*)\}\}|
    (?P<braced>[_a-z][_a-z0-9]*)\}\}|
    (?P<invalid>)
    )
    '''
