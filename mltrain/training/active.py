from typing import Optional
from mltrain.log import logger


"""
if active_e_thresh is None:
    if active_method.lower() == 'diff':
        #                 1 kcal mol-1 molecule-1
        active_e_thresh = 0.043363 * len(mlp.system.molecules)

    if active_method.lower() == 'gp_var':
        # Threshold for maximum per-atom GP variance (eV atom^-1)
        active_e_thresh = 1E-5
"""


def train(mlp:               'mltrain.potentials.MLPotential',
          method_name:       str,
          max_active_time:   float = 1000,
          n_configs_iter:    int = 10,
          temp:              float = 300.0,
          active_e_thresh:   Optional[float] = None,
          active_method:     str = 'diff',
          max_e_threshold:   Optional[float] = None,
          max_active_iters:  int = 50,
          n_init_configs:    int = 10,
          init_configs:      Optional['mltrain.ConfigurationSet'] = None,
          fix_init_config:   bool = False,
          bbond_energy:      Optional[dict] = None,
          fbond_energy:      Optional[dict] = None,
          init_active_temp:  Optional[float] = None,
          min_active_iters:  int = 1) -> None:
    """
    Train a system using active learning, by propagating dynamics using ML
    driven molecular dynamics (MD) and adding configurations based on some
    selection criteria. Loop looks something like

    Generate configurations -> train a MLP -> run MLP-MD -> frames
                                   ^                             |
                                   |________ calc true  _________


    Active learning will loop until either:
        (1) the iteration > max_active_iters
        (2) no configurations are found to add

    --------------------------------------------------------------------------
    Arguments:
        mlp: Machine learned potential to train

        method_name: Name of a reference method to use as the ground truth e.g.
                     dftb, orca, gpaw

    Keyword Arguments:
        max_active_time: (float) Maximum propagation time in the active
                            learning loop. Default = 1 ps

        n_configs_iter: (int) Number of configurations to generate per
                        active learning cycle

        temp: (float) Temperature in K to propagate active learning at -
              higher is better for stability but requires more training


        active_method: (str) Method used to generate active learnt
                       configurations. One of ['diff', 'gp_var']

        active_e_thresh: (float) Threshold in eV (E_t) above which a
                            configuration is added to the potential. If None
                            then will use 1 kcal mol-1 molecule-1

                            1. active_method='diff': |E_0 - E_MLP| > E_t

                            3. active_method='gp_var': σ^2_GAP(predicted) > E_t

        max_e_threshold: (float) Maximum relative energy threshold for
                           configurations to be added to the training data

        max_active_iters: (int) Maximum number of active learning
                          iterations to perform. Will break if we hit the
                          early stopping criteria

        n_init_configs: (int) Number of initial configurations to generate,
                        will be ignored if init_configs is not None

        init_configs: (gt.ConfigurationSet) A set of configurations from
                      which to start the active learning from


        fix_init_config: (bool) Always start from the same initial
                         configuration for the active learning loop, if
                         False then the minimum energy structure is used.
                         Useful for TS learning, where dynamics should be
                         propagated from a saddle point not the minimum

        bbond_energy: (dict | None) Additional energy to add to a breaking
                      bond. e.g. bbond_energy={(0, 1), 0.1} Adds 0.1 eV
                      to the 'bond' between atoms 0 and 1 as velocities
                     shared between the atoms in the breaking bond direction

        fbond_energy: (dict | None) As bbond_energy but in the direction to
                      form a bond

        init_active_temp: (float | None) Initial temperature for velocities
                          in the 'active' MD search for configurations

        min_active_iters: (int) Minimum number of active iterations to
                             perform
    """
    _gen_init_training_configs(init_configs=init_configs,
                               num=n_init_configs,
                               method_name=method_name,
                               system=mlp.system)
    mlp.train()

    # Run the active learning loop, running iterative GAP-MD
    for iteration in range(max_active_iters):

        curr_n_configs = len(mlp.training_data)

        _add_active_configs(mlp,
                            init_config=(mlp.training_data[0] if fix_init_config
                                         else mlp.training_data.lowest_energy),
                            ref_method_name=method_name,
                            method=str(active_method),
                            n_configs=n_configs_iter,
                            temp=temp,
                            e_thresh=active_e_thresh,
                            max_time_fs=max_active_time,
                            bbond_energy=bbond_energy,
                            fbond_energy=fbond_energy,
                            init_temp=init_active_temp)

        # Active learning finds no configurations,,
        if len(mlp.training_data) == curr_n_configs and iteration > min_active_iters:
            logger.info('No AL configurations found. Final dataset size '
                        f'= {curr_n_configs} Active learning = DONE')
            break

        # If required, remove high-lying energy configuration from the data
        if max_e_threshold is not None:
            mlp.training_data.remove_above_e(max_e_threshold)

        mlp.train()

    return None