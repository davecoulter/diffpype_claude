import cfut
import subprocess
import concurrent.futures

executors = {
                    'local': concurrent.futures.ProcessPoolExecutor,
                    'slurm': cfut.SlurmExecutor,
                    'condor': cfut.CondorExecutor
            }


class Executor:

    def __init__(self, kind='local', debug=False, keep_logs=False):

        self.exec_kind = kind
        self.debug = debug
        self.keep_logs = keep_logs

        self.ex = executors[self.exec_kind]()

        return 
