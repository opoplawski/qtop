import logging
import os
import errno
import tempfile
import tarfile
import sys
import constants
import glob
import datetime


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def check_empty_file(orig_file):
    if os.path.getsize(orig_file) == 0:
        raise FileEmptyError(orig_file)


def get_new_temp_file(suffix, prefix, config=None):  # **kwargs
    """
    Using mkstemp instead of NamedTemporaryFile because a file descriptor
    is needed to redirect sys.stdout to.
    """
    savepath = config['savepath'] if config else None
    fd, temp_filepath = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=savepath)  # **kwargs
    logging.debug('temp_filepath: %s' % temp_filepath)
    # out_file = os.fdopen(fd, 'w')
    return fd, temp_filepath


def safe_exit_with_file_close(handle, name, stdout, options, config,
                              qtop_logfile, sample_filename, delete_file=False):
    sys.stdout.flush()
    sys.stdout.close()
    os.close(handle)
    if delete_file:
        os.unlink(name)  # this deletes the file
    # sys.stdout = stdout
    if options.SAMPLE >= 1:
        add_to_sample([qtop_logfile], config['savepath'], sample_filename)
    sys.exit(0)


def init_sample_file(options, config, SAMPLE_FILENAME, scheduler_output_filenames, QTOPCONF_YAML, QTOPPATH):
    """
    If the user wants to give feedback to the developers for a bugfix via the -L cmdline switch,
    this initialises a tar file, and adds:
    * the scheduler output files (-L),
    * and source files (-LL)
    to the tar file
    """
    savepath = constants.savepath
    if options.SAMPLE >= 1:
        # clears any preexisting tar files
        tar_out = tarfile.open(os.path.join(config['savepath'], SAMPLE_FILENAME), mode='w')
        tar_out.close()
        # add all scheduler output files to sample
        [add_to_sample([scheduler_output_filenames[fn]], savepath, SAMPLE_FILENAME)
         for fn in scheduler_output_filenames if os.path.isfile(scheduler_output_filenames[fn])]

    if options.SAMPLE >= 2:
        add_to_sample([os.path.join(os.path.realpath(QTOPPATH), QTOPCONF_YAML)], savepath, SAMPLE_FILENAME)
        source_files = glob.glob(os.path.join(os.path.realpath(QTOPPATH), '*.py'))
        add_to_sample(source_files, savepath, SAMPLE_FILENAME, subdir='qtop_py')


def add_to_sample(filepaths_to_add, savepath, sample_file, sample_method=tarfile, subdir=None):
    """
    opens sample_file in path savepath and adds files filepaths_to_add
    """
    assert isinstance(filepaths_to_add, list)
    sample_out = sample_method.open(os.path.join(savepath, sample_file), mode='a')
    for filepath_to_add in filepaths_to_add:
        path, fn = filepath_to_add.rsplit('/', 1)
        try:
            logging.debug('Adding %s to sample...' % filepath_to_add)
            sample_out.add(filepath_to_add, arcname=fn if not subdir else os.path.join(subdir, fn))
        except tarfile.TarError:  # TODO: test what could go wrong here
            logging.error('There seems to be something wrong with the tarfile. Skipping...')
    else:
        logging.debug('Closing sample...')
        sample_out.close()


def get_sample_filename(SAMPLE_FILENAME, config):
    if config['overwrite_sample_file']:
        SAMPLE_FILENAME = SAMPLE_FILENAME % {'datetime': ''}
    else:
        SAMPLE_FILENAME = SAMPLE_FILENAME \
                               % {'datetime': '_' + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}
    return SAMPLE_FILENAME


class FileNotFound(Exception):
    def __init__(self, fn):
        msg = "File %s not found.\nMaybe the correct scheduler is not specified?" % fn
        Exception.__init__(self, msg)
        logging.critical(msg)
        self.fn = fn


class FileEmptyError(Exception):
    def __init__(self, fn):
        msg = "File %s is empty.\n" \
              "Is your batch scheduler loaded with jobs?" % fn
        Exception.__init__(self, msg)
        logging.warning(msg)
        self.fn = fn


def deprecate_old_output_files(config):
    """
    deletes older json and .out files in savepath directory.
    """
    time_alive = get_timedelta(parse_time_input(config['auto_delete_old_output_files_after']))
    user_selected_save_path = os.path.realpath(os.path.expandvars(config['savepath']))
    for f in os.listdir(user_selected_save_path):
        if (not f.endswith(('json', '.out'))) or f.endswith('rec.out'):
            continue
        curpath = os.path.join(user_selected_save_path, f)
        file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
        if datetime.datetime.now() - file_modified > time_alive:
            os.remove(curpath)


def get_timedelta(extra_kw_args):
    """
    This solely exists to allow timedelta.timedelta's keyword argument (minutes/seconds/hours=...)
    to be selected with a variable.
    """
    return datetime.timedelta(**extra_kw_args)


def parse_time_input(_time):
    """
    the func accepts a _time str in either (h)ours, (m)inutes, or (s)econds, using the respective suffix,
    e.g. '5h', or '10m', or '30s'
    A tuple is returned, e.g. (5, 'hours')
    """
    assert _time.endswith(('h', 'm', 's'))
    try:
        int(_time[:-1])
    except ValueError:
        logging.critical('Time input given must be a number followed by the letter h/m/s. Exiting.')

    quantity, user_unit_suffix = _time[:-1], _time[-1]
    units = {'m': 'minutes', 's': 'seconds', 'h': 'hours'}
    user_unit = units[user_unit_suffix]

    return {user_unit: int(quantity)}
