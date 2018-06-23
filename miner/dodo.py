# global configuration set outside
builder = None


def _get_sub_task(name, generator, task_dep=None) -> dict:
    """
    Create doit task from generator

    The generator returns dictionary with doit task description.
    An action is a side effect of the generator returning end of iteration.

    The task description is get in planning phase and same variables may not be up to date. Usually uptodate action
    should be deferred with callable which is called before action should be executed.

    The action from generator is called only when sub-task is not up to date. Otherwise the action is never called.

    :param name:
        Name of sub-task or None.
    :param generator:
        Generator returning task description.
    :param task_dep:
        List of task dependencies.
    :return:
        Task description compatible with doit.
    """
    task = next(generator)
    # create callable object using lambda to defer action to execution phase.
    task.update({'actions': [lambda: next(generator, None)]})
    if name:
        task.update({'name': name})
    if task_dep:
        task.update({'task_dep': task_dep})
    return task


def task_clone():
    """
    Task responsible for initial cloning of all repositories
    """
    for clone_repo in builder.clone_repos():
        yield _get_sub_task(None, clone_repo)


def task_checkout():
    """
    Task responsible for switching all repositories to requested branch or commit
    """
    for checkout_repo in builder.checkout_repos():
        yield _get_sub_task(None, checkout_repo, ['clone'])


def task_prepare():
    """
    Task responsible for preparation of LEDE build system
    """
    yield _get_sub_task('feeds_conf', builder.prepare_feeds_conf(), ['checkout'])
    yield _get_sub_task('feeds_update', builder.prepare_feeds_update(), ['prepare:feeds_conf'])

    feeds_tasks = []
    for prepare_feeds in builder.prepare_feeds():
        task = _get_sub_task(None, prepare_feeds, ['prepare:feeds_update'])
        task['name'] = 'feeds_install:{}'.format(task['name'])
        feeds_tasks.append('prepare:{}'.format(task['name']))
        yield task

    yield _get_sub_task('default_config', builder.prepare_default_config(), feeds_tasks)
    yield _get_sub_task('config', builder.prepare_config(), ['prepare:default_config'])

    for prepare_key in builder.prepare_keys():
        yield _get_sub_task(None, prepare_key, ['prepare:config'])
