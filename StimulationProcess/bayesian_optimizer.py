import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colormaps as cm
from skopt import gp_minimize
from skopt.space import Real
from scipy.interpolate import interp1d

import biorbd
from pysciencemode import Modes


class BayesianOptimizer():
    def __init__(self, visualization_widget):

        self.visualization_widget = visualization_widget

        # Define the model
        self.model = visualization_widget.model
        self.nb_dof = self.model.nbQ()

        # Define the variable bounds
        self.bounds = [
            Real(20, 50, name='R_frequency'),  # Hz
            Real(8, 20, name='R_intensity'),  # mA
            Real(200, 500, name='R_width'),  # micros
            Real(20, 50, name='L_frequency'),  # Hz
            Real(8, 20, name='L_intensity'),  # mA
            Real(200, 500, name='L_width'),  # micros
        ]

        # Define the objective weightings
        # TODO: Charbie -> how do we chose which objectives to minimize ?
        self.weight_comddot = 1
        self.weight_angular_momentum = 1
        self.weight_enegy = 1


    def compute_mean_cycle(self, cycles):

        read_frequency = 100  # Hz  # TODO: @ophelielariviere, is it always 100 Hz ?
        nb_frames = [cycles['nb_frames'][-i_cycle] for i_cycle in range(10)]
        nb_interpolation_frames = np.mean(np.array(nb_frames))
        q_interpolated = np.zeros((self.nb_dof, nb_interpolation_frames, 10))
        qdot_interpolated = np.zeros((self.nb_dof, nb_interpolation_frames, 10))
        qddot_interpolated = np.zeros((self.nb_dof, nb_interpolation_frames, 10))
        tau_interpolated = np.zeros((self.nb_dof, nb_interpolation_frames, 10))
        for i_cycle in range(10):
            current_q = cycles['q'][-i_cycle]
            current_qdot = cycles['qdot'][-i_cycle]
            current_qddot = cycles['qddot'][-i_cycle]
            current_tau = cycles['tau'][-i_cycle]
            current_nb_frames = len(current_q)
            time_vector = np.linspace(0, (current_nb_frames-1) * 1/read_frequency, current_nb_frames)
            time_vector_interpolated = np.linspace(0, (current_nb_frames-1) * 1/read_frequency, nb_interpolation_frames)

            interp_func_q = interp1d(current_q, time_vector, kind='cubic')
            interp_func_qdot = interp1d(current_qdot, time_vector, kind='cubic')
            interp_func_qddot = interp1d(current_qddot, time_vector, kind='cubic')
            interp_func_tau = interp1d(current_tau, time_vector, kind='cubic')

            q_interpolated[:, :, i_cycle] = interp_func_q(time_vector_interpolated)
            qdot_interpolated[:, :, i_cycle] = interp_func_qdot(time_vector_interpolated)
            qddot_interpolated[:, :, i_cycle] = interp_func_qddot(time_vector_interpolated)
            tau_interpolated[:, :, i_cycle] = interp_func_tau(time_vector_interpolated)

        q_mean = np.mean(q_interpolated, axis=2)
        qdot_mean = np.mean(qdot_interpolated, axis=2)
        qddot_mean = np.mean(qddot_interpolated, axis=2)
        tau_mean = np.mean(tau_interpolated, axis=2)

        return q_mean, qdot_mean, qddot_mean, tau_mean


    def make_an_iteration(self, params):

        # Current values of the optimized FES parameters
        R_frequency = params[0]
        R_intensity = params[1]
        R_width = params[2]
        L_frequency = params[3]
        L_intensity = params[4]
        L_width = params[5]

        # Send FES with these parameter values
        # Setup Right leg
        self.visualization_widget.set_chanel_inputs(channel=0,
                                                    channel_layout=None,
                                                    name_input="Right",
                                                    amplitude_input=R_intensity,  # TODO: @ophelielariviere, is it the right parameter ?
                                                    pulse_width_input=R_width,
                                                    frequency_input=R_frequency,
                                                    mode_input=Modes.SINGLE)
        # Setup Left leg
        self.visualization_widget.set_chanel_inputs(channel=1,
                                                    channel_layout=None,
                                                    name_input="Left",
                                                    amplitude_input=L_intensity,  # TODO: @ophelielariviere, is it the right parameter ?
                                                    pulse_width_input=L_width,
                                                    frequency_input=L_frequency,
                                                    mode_input=Modes.SINGLE)
        # Stimulate
        self.visualization_widget.start_stimulation(self, [0, 1])

        # Collect data while waiting for the subject to get a stable walking pattern with these parameters
        cycles = {'StanceDuration_L': [],
            'StanceDuration_R': [],
            'Cycleduration': [],
            'StepWidth': [],
            'StepLength_L': [],
            'StepLength_R': [],
            'PropulsionDuration_L': [],
            'PropulsionDuration_R': [],
            'Cadence': [],
            'q' : [],
            # 'int_q': [],
            'qdot': [],
            # 'int_qdot': [],
            'qddot': [],
            # 'int_qddot': [],
            'tau': [],
            # 'int_tau': [],
            'nb_frames': []}
        old_cycledata = None
        new_cycledata = "Fake_data"
        stable = False
        while not stable:
            while old_cycledata == new_cycledata:  # No new data to collect
                new_cycledata = self.visualization_widget.buffer.get()
                time.sleep(0.1)
            # Add the new cycle data to the list of cycles
            new_gait_parameters = new_cycledata['gait_parameter']
            new_q = new_cycledata['Angle']
            new_qdot = new_cycledata['VitAng']
            new_qddot = new_cycledata['AccAng']
            new_tau = new_cycledata['Tau']
            cycles['StanceDuration_L'] += new_gait_parameters['StanceDuration_L']
            cycles['StanceDuration_R'] += new_gait_parameters['StanceDuration_R']
            cycles['Cycleduration'] += new_gait_parameters['Cycleduration']
            cycles['StepWidth'] += new_gait_parameters['StepWidth']
            cycles['StepLength_L'] += new_gait_parameters['StepLength_L']
            cycles['StepLength_R'] += new_gait_parameters['StepLength_R']
            cycles['PropulsionDuration_L'] += new_gait_parameters['PropulsionDuration_L']
            cycles['PropulsionDuration_R'] += new_gait_parameters['PropulsionDuration_R']
            cycles['Cadence'] += new_gait_parameters['Cadence']
            cycles['q'] += new_q
            # cycles['int_q'] += np.sum(new_q)
            cycles['qdot'] += new_qdot
            # cycles['int_qdot'] += np.sum(new_qdot)
            cycles['qddot'] += new_qddot
            # cycles['int_qddot'] += np.sum(new_qddot)
            cycles['tau'] += new_tau
            # cycles['int_tau'] += np.sum(new_tau)
            cycles['nb_frames'] += new_q.shape[1]
            if len(cycles['Cycleduration']) > 10:
                # Compute the std of the last 10 cycles
                StanceDuration_L_std = np.nanstd(cycles['StanceDuration_L'][-10:])
                StanceDuration_R_std = np.nanstd(cycles['StanceDuration_R'][-10:])
                Cycleduration_std = np.nanstd(cycles['Cycleduration'][-10:])
                StepWidth_std = np.nanstd(cycles['StepWidth'][-10:])
                StepLength_L_std = np.nanstd(cycles['StepLength_L'][-10:])
                StepLength_R_std = np.nanstd(cycles['StepLength_R'][-10:])
                PropulsionDuration_L_std = np.nanstd(cycles['PropulsionDuration_L'][-10:])
                PropulsionDuration_R_std = np.nanstd(cycles['PropulsionDuration_R'][-10:])
                Cadence_std = np.nanstd(cycles['Cadence'][-10:])
                # int_q_std = np.nanstd(cycles['int_q'][-10:])
                # int_qdot_std = np.nanstd(cycles['int_qdot'][-10:])
                # int_qddot_std = np.nanstd(cycles['int_qddot'][-10:])
                # int_tau_std = np.nanstd(cycles['int_tau'][-10:])

                # Check if the last 10 cycles are stable
                stable = (StanceDuration_L_std < 0.05 and  # 5% of the cycle
                          StanceDuration_R_std < 0.05 and  # 5% of the cycle
                          Cycleduration_std < 0.05 and  # 5% of the cycle
                          StepWidth_std < 0.05 and  # 5cm
                          StepLength_L_std < 0.05 and  # 5cm
                          StepLength_R_std < 0.05 and  # 5cm
                          PropulsionDuration_L_std < 0.05 and  # 5% of the cycle
                          PropulsionDuration_R_std < 0.05 and  # 5% of the cycle
                          Cadence_std < 5)  # and  # TODO: confirm 5 steps per minute ?
                          # int_q_std < 50 and  # TODO: confirm threshold
                          # int_qdot_std < 50 and   # TODO: confirm threshold
                          # int_qddot_std < 50 and  # TODO: confirm threshold
                          # int_tau_std < 50)  # TODO: confirm threshold
            old_cycledata = new_cycledata

        # Stop the stimulation
        self.visualization_widget.pause_stimulation()

        # Compute the mean cycle
        q_mean, qdot_mean, qddot_mean, tau_mean = self.compute_mean_cycle(cycles)

        # Compute objective values
        objective_value = self.objective(self.model, q_mean, qdot_mean, qddot_mean, tau_mean, R_intensity, L_intensity)

        return objective_value

    @staticmethod
    def compute_com_acceleration(model: biorbd.Model, q: np.ndarray, qdot: np.ndarray, qddot: np.ndarray):

        nb_frames = q.shape[1]

        comddot = np.zeros((nb_frames,))
        for i_frame in range(nb_frames):
            comddot[i_frame] = np.linalg.norm(
                model.CoMddot(q[:, i_frame], qdot[:, i_frame], qddot[:, i_frame]).to_array())

        return comddot

    @staticmethod
    def compute_angular_momentum(model: biorbd.Model, q: np.ndarray, qdot: np.ndarray, qddot: np.ndarray):

        nb_frames = q.shape[1]

        angular_momentum = np.zeros((nb_frames,))
        for i_frame in range(nb_frames):
            angular_momentum[i_frame] = np.linalg.norm(
                model.angularMomentum(q[:, i_frame], qdot[:, i_frame]).to_array())

        return angular_momentum

    @staticmethod
    def compute_energy(qdot, tau, R_intensity, L_intensity, time_vector):
        """
        Since the time is the same, min energy and power gives the same thing (same min).
        """

        voltage = 30  # TODO: @ophelielariviere, what is the voltage ?
        power_stim = np.abs(R_intensity * voltage) + np.abs(L_intensity * voltage)
        power_total = np.sum(np.abs(tau * qdot), axis=0)
        power_human = power_total - power_stim
        energy_human = np.trapezoid(power_human, x=time_vector)

        return energy_human

    def objective(self, model, q, qdot, qddot, tau, R_intensity, L_intensity):

        nb_frames = q.shape[1]
        read_frequency = 100  # Hz  # TODO: @ophelielariviere, is it always 100 Hz ?
        time_vector = np.linspace(0, (nb_frames-1) * 1/read_frequency, nb_frames)

        comddot = self.compute_com_acceleration(model, q, qdot, qddot)
        angular_momentum = self.compute_angular_momentum(model, q, qdot, qddot)
        energy_human = self.compute_energy(qdot, tau, R_intensity, L_intensity, time_vector)

        return self.weight_comddot * comddot + self.weight_angular_momentum * angular_momentum + self.weight_enegy * energy_human


    def perform_bayesian_optim(self):
        """Perform Bayesian optimization using Gaussian Processes."""

        # Activate the stimulator # TODO: @ophelielariviere: with default values for the parameters ?
        self.visualization_widget.activate_stimulateur()

        # gp_minimize will try to find the minimal value of the objective function.
        result = gp_minimize(
            func =lambda params: self.make_an_iteration(params),
            dimensions=self.bounds,
            n_calls=100,         # number of evaluations of f
            acq_func="LCB",      # "LCB", "EI", "PI", "gp_hedge", "EIps", "PIps"
            kappa=5,  # *
            random_state=0,  #*
            n_jobs=1,
        )  #x0, y0, kappa[exploitation, exploration], xi [minimal improvement default 0.01]
        # TODO: stop when the same point has been hit t time (t=5 in general)
        return result

    def save_optimal_bayesian_parameters(self, result):
        save_file_name = self.visualization_widget.path_to_saveData + 'optimal_bayesian_parameters.txt'
        with open(save_file_name, 'w') as f:
            f.write("Optimal parameters found through Bayesian optimization : \n\n")
            f.write("Frequency right = %.4f\n" % result.x[0])
            f.write("Intensity right = %.4f\n" % result.x[1])
            f.write("Width right = %.4f\n" % result.x[2])
            f.write("Frequency left = %.4f\n" % result.x[3])
            f.write("Intensity left = %.4f\n" % result.x[4])
            f.write("Width left = %.4f\n" % result.x[5])
            f.write("\nOptimal cost function value = %.4f\n" % result.fun)
        return

    def plot_bayesian_optim_results(self, result):
        print("Best found minimum:")
        print("X = %.4f, Y = %.4f" % (result.x[0], result.x[1]))
        print("f(x,y) = %.4f" % result.fun)

        # Optionally, plot convergence
        fig = plt.figure(figsize=(12, 5))
        ax0 = fig.add_subplot(131)
        ax1 = fig.add_subplot(132, projection="3d")
        ax2 = fig.add_subplot(133, projection="3d")

        # Convergence plot
        ax0.plot(result.func_vals, marker='o')
        ax0.set_title('Convergence Plot')
        ax0.set_xlabel('Number of calls')
        ax0.set_ylabel('Objective function value')

        # Plot the function sampling on the right side
        x_iters_array = np.array(result.x_iters)
        func_vals_array = np.array(result.func_vals)
        colors_min = np.min(func_vals_array)
        colors_max = np.max(func_vals_array)
        normalized_cmap = (func_vals_array - colors_min) / (colors_max - colors_min)
        colors = cm["viridis"](normalized_cmap)
        p1 = ax1.scatter(x_iters_array[:, 0], x_iters_array[:, 1], x_iters_array[:, 2], c=colors, marker='.')
        ax1.set_xlabel('Frequency')
        ax1.set_ylabel('Intensity')
        ax1.set_zlabel('Width')
        ax1.set_title('Function sampling Right')

        # Plot the function sampling on the left side
        p2 = ax2.scatter(x_iters_array[:, 3], x_iters_array[:, 4], x_iters_array[:, 5], c=colors, marker='.')
        ax2.set_xlabel('Frequency')
        ax2.set_ylabel('Intensity')
        ax2.set_zlabel('Width')
        ax2.set_title('Function sampling Left')

        cbar = fig.colorbar(p1)
        cbar.set_label('Objective function value')
        plt.show()
