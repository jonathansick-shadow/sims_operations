#!/usr/bin/env python

##########################################################################
# This script and all of the supporting infrastructure is taken from the
# qserv package with much appreciation! It was modified to fit the needs
# of this package.
##########################################################################

import argparse
import ConfigParser
import fileinput
from lsst.sims.operations.admin import configure, commons
import logging
import os
import shutil
from subprocess import check_output
import sys


def parseArgs():
    default_opsim_run_dir = os.path.join(os.path.expanduser("~"), "opsim-run")

    description = """\
                    opsim configuration tool. Creates an execution
                    directory (opsim_run_dir) which will contains
                    configuration and execution data for a given opsim
                    instance. Deploys values from meta-config file
                    $opsim_run_dir/opsim-meta.conf in all opsim configuration
                    files and databases. Default behaviour will configure a
                    mono-node instance in %s. IMPORTANT : --all MUST BE USED
                    FOR A SETUP FROM SCRATCH.
                    """

    parser = argparse.ArgumentParser(description=description %
                                     default_opsim_run_dir,
                                     formatter_class=
                                     argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-a", "--all", dest="all", action='store_true',
                        default=False,
                        help="clean execution directory and then run all"
                        "configuration steps")

    # Defining option of each configuration step
    for step_name in configure.STEP_LIST:
        parser.add_argument("-{0}".format(configure.STEP_ABBR[step_name]),
                            "--{0}".format(step_name),
                            dest="step_list",
                            action='append_const',
                            const=step_name,
                            help=configure.STEP_DOC[step_name])

    # Logging management
    verbose_dict = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'FATAL': logging.FATAL,
    }
    verbose_arg_values = verbose_dict.keys()
    parser.add_argument("-v", "--verbose-level", dest="verbose_str",
                        choices=verbose_arg_values,
                        default='INFO',
                        help="verbosity level")

    # forcing options which may ask user confirmation
    parser.add_argument("-f", "--force", dest="force", action='store_true',
                        default=False,
                        help="forcing removal of existing execution data")

    # run dir, all mutable data related to a opsim running instance are
    # located here
    parser.add_argument("-R", "--opsim-run-dir", dest="opsim_run_dir",
                        default=default_opsim_run_dir,
                        help="full path to opsim_run_dir")

    # meta-configuration file whose parameters will be dispatched in opsim
    # services configuration files
    args = parser.parse_args()
    default_meta_config_file = os.path.join(args.opsim_run_dir,
                                            "opsim-meta.conf")
    parser.add_argument("-m", "--metaconfig", dest="meta_config_file",
                        default=default_meta_config_file,
                        help="full path to opsim meta-configuration file")

    args = parser.parse_args()

    if args.all:
        args.step_list = configure.STEP_LIST
    elif args.step_list is None:
        args.step_list = configure.STEP_RUN_LIST

    args.verbose_level = verbose_dict[args.verbose_str]

    return args


def main():

    args = parseArgs()

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=args.verbose_level)

    logging.info("opsim configuration tool\n" +
                 "=======================================" +
                 "================================")

    opsim_dir = os.path.abspath(os.path.join(
                                os.path.dirname(os.path.realpath(__file__)),
                                ".."))

    if configure.PREPARE in args.step_list:

        if os.path.exists(args.opsim_run_dir):
            if args.force or configure.user_yes_no_query(
                    "WARNING : Do you want to erase all configuration" +
                    " data in {0} ?".format(args.opsim_run_dir)):
                shutil.rmtree(args.opsim_run_dir)
            else:
                logging.info("Stopping opsim configuration, please specify an "
                             "other configuration directory")
                sys.exit(1)

        in_config_dir = os.path.join(opsim_dir, "cfg")
        in_template_config_dir = os.path.join(in_config_dir, "templates")
        out_template_config_dir = os.path.join(args.opsim_run_dir, "templates")
        logging.info("Copying template configuration from {0} to {1}"
                     .format(in_template_config_dir, args.opsim_run_dir))
        shutil.copytree(in_template_config_dir, out_template_config_dir)

        in_meta_config_file = os.path.join(in_config_dir, "opsim-meta.conf")
        logging.info("Creating meta-configuration file: {0}"
                     .format(args.meta_config_file))
        params_dict = {
            'RUN_BASE_DIR': args.opsim_run_dir
        }
        configure.apply_tpl(in_meta_config_file, args.meta_config_file,
                            params_dict)

    def intersect(seq1, seq2):
        '''
        returns subset of seq1 which is contained in seq2 keeping original
        ordering of items
        '''
        seq2 = set(seq2)
        return [item for item in seq1 if item in seq2]

    def contains_configuration_step(step_list):
        return bool(intersect(step_list, configure.STEP_RUN_LIST))

    ###################################
    #
    # Running configuration procedure
    #
    ###################################
    if contains_configuration_step(args.step_list):
        try:
            logging.info("Reading meta-configuration file {0}"
                         .format(args.meta_config_file))
            config = commons.read_config(args.meta_config_file)

            # used in templates targets comments
            config['opsim']['meta_config_file'] = args.meta_config_file

        except ConfigParser.NoOptionError, exc:
            logging.fatal("Missing option in meta-configuration file: %s", exc)
            sys.exit(1)

        if configure.DIRTREE in args.step_list:
            logging.info("Defining main directory structure")
            configure.check_root_dirs()
            configure.check_root_symlinks()

        ##########################################
        #
        # Creating opsim services configuration
        # using templates and meta_config_file
        #
        ##########################################
        run_base_dir = config['opsim']['run_base_dir']
        if configure.ETC in args.step_list:
            logging.info("Creating configuration files in {0}"
                         .format(os.path.join(run_base_dir, "etc")) +
                         " and scripts in {0}"
                         .format(os.path.join(run_base_dir, "tmp")))
            template_root = os.path.join(run_base_dir, "templates")
            dest_root = os.path.join(run_base_dir)
            configure.apply_templates(template_root, dest_root)

        components_to_configure = intersect(args.step_list,
                                            configure.COMPONENTS)
        if len(components_to_configure) > 0:
            logging.info("Running configuration scripts")
            configuration_scripts_dir = os.path.join(run_base_dir, 'tmp',
                                                     'configure')

            for comp in components_to_configure:
                cfg_script = os.path.join(configuration_scripts_dir,
                                          comp + ".sh")
                if os.path.isfile(cfg_script):
                    commons.run_command([cfg_script])

            def client_cfg_from_tpl(product):
                homedir = os.path.expanduser("~")
                if product == configure.OPSIM:
                    filename = "opsim-client.conf"
                    cfg_link = os.path.join(homedir, ".lsst", "opsim.conf")
                elif product == configure.MYSQL:
                    filename = "my-client.cnf"
                    cfg_link = os.path.join(homedir, ".my.cnf")
                else:
                    logging.fatal("Unable to apply configuration template for "
                                  "product %s", product)
                    sys.exit(1)

                template_file = os.path.join(
                    run_base_dir, "templates", "etc", filename
                )
                cfg_file = os.path.join(
                    run_base_dir, "etc", filename
                )
                configure.apply_tpl(
                    template_file,
                    cfg_file
                )
                logging.info(
                    "Client configuration file created : {0}".format(cfg_file)
                )

                if os.path.isfile(cfg_link) and os.lstat(cfg_link):

                    try:
                        is_symlink_correct = os.path.samefile(cfg_link,
                                                              cfg_file)
                    except os.error:
                        # link is broken
                        is_symlink_correct = False

                    if not is_symlink_correct:
                        if args.force or configure.user_yes_no_query(
                            ("Do you want to update link to {0} user "
                             "configuration file ".format(product) +
                             "(currently pointing to {0}) with {1}?"
                             .format(os.path.realpath(cfg_link), cfg_file))):
                            os.remove(cfg_link)
                            os.symlink(cfg_file, cfg_link)
                        else:
                            logging.info("Client configuration unmodified. "
                                         "Exiting.")
                            sys.exit(1)

                else:

                    if product == configure.OPSIM:
                        # might need to create directory first
                        try:
                            os.makedirs(os.path.join(homedir, ".lsst"))
                            logging.debug("Creating client configuration "
                                          "directory : ~/.lsst")
                        except os.error:
                            pass

                    try:
                        os.remove(cfg_link)
                        logging.debug("Removing broken symbolic link : {0}"
                                      .format(cfg_link))
                    except os.error:
                        pass

                    os.symlink(cfg_file, cfg_link)

                logging.info(
                    "{0} is now pointing to : {1}".format(cfg_link, cfg_file)
                )

            if configure.MYSQL in args.step_list:
                client_cfg_from_tpl(configure.MYSQL)

            if configure.CLIENT in args.step_list:
                client_cfg_from_tpl(configure.OPSIM)

if __name__ == '__main__':
    main()
