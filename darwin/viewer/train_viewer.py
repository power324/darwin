import time
import glfw
import numpy as np
from operator import itemgetter
import time
from mujoco_py import const, MjViewer
from utils.util import listdict2dictnp, split_obs, convert_obs
from os import path
import torch
import matplotlib.pyplot as plt
import gym

STEPS = 1000
EPISODES = 100


def splitobs(obs, keepdims=True):
    '''
        Split obs into list of single agent obs.
        Args:
            obs: dictionary of numpy arrays where first dim in each array is agent dim
    '''
    n_agents = obs[list(obs.keys())[0]].shape[0]
    return [{k: v[[i]] if keepdims else v[i] for k, v in obs.items()} for i in range(n_agents)]


class TrainViewer(MjViewer):
    def __init__(self, env, policies, policy_type='dqn', show_render=True, save_policy=False, seed=None, duration=None, episodes=EPISODES, steps=STEPS):
        if seed is None:
            self.seed = env.seed()[0] 
        else:
            self.seed = seed
            env.seed(seed)
        
        self.env = env
        self.policies = policies
        self.policy_type = policy_type
        self.show_render = show_render
        self.save_policy = save_policy
        self.duration = duration
        self.steps = steps
        self.episodes = episodes
        

        self.total_rew = 0.
        self.ob = env.reset()
        self.ob_copy = self.ob

        self.saved_state = self.env.unwrapped.sim.get_state()
        # for policy in self.policies:
        #     policy.reset()
        
        assert self.env.metadata['n_agents'] % len(self.policies) == 0
        if hasattr(self.env, "reset_goal"):
            self.goal = env.reset_goal()
        super().__init__(self.env.unwrapped.sim)

        # TO DO: remove circular dependency on viewer object. It looks fishy.
        self.env.unwrapped.viewer = self
        if self.render and self.show_render:
            self.env.render()

    def key_callback(self, window, key, scancode, action, mods):
        super().key_callback(window, key, scancode, action, mods)
        # Trigger on keyup only:
        if action != glfw.RELEASE:
            return
        # Increment experiment seed
        if key == glfw.KEY_N:
            self.reset_increment()
        # Decrement experiment trial
        elif key == glfw.KEY_P:
            print("Pressed P")
            self.seed = max(self.seed - 1, 0)
            self.env.seed(self.seed)
            self.ob = self.env.reset()
            for policy in self.policies:
                policy.reset()
            if hasattr(self.env, "reset_goal"):
                self.goal = self.env.reset_goal()
            self.update_sim(self.env.unwrapped.sim)


    def run(self):
        self.total_rew_avg = 0.0
        self.n_episodes = 0
        self.rewards = []
        self.reward_plot = []
        self.loss_plot = []
        self.save_policy_model = False
        count = 0 
        self.ob=self.env.reset()
        
        for episode in range(self.episodes):
            print('#######################')
            print('Episode # {}'.format(episode))
            print('#######################')
            self.ob = self.env.reset()
            print("self.ob:",self.ob)
            print("Self.action:",self.env.action_space())
            for step in range(self.steps):

                print(f"Training DQN - Episode: {episode} Step: {step}")

                if self.save_policy:
                    if (episode == self.episodes - 1) and (step == 0):
                        self.save_policy_model = True

                self.ob, rew, done, env_info,loss = policy_types[self.policy_type](self.policies, 
                                                                                self.env, 
                                                                                self.ob, 
                                                                                self.perform_render,
                                                                                step,
                                                                                self.save_policy_model)
                print("rew:",rew)
                print("count:",count)
                if (count >= 1000) and (count % 10 == 0):
                    self.loss_plot.append(loss)
                    self.reward_plot.append(rew)
                    self.total_rew += rew
                
                if done or env_info.get('discard_episode', False):
                    self.reset_increment()
                    self.env.unwrapped.sim.set_state(self.saved_state)
                    self.ob = self.ob_copy
                    # Exit this episode
                    break
                
                count += 1
            
                
                self.perform_render()
               
                
            self.rewards.append(self.total_rew)

        
        self.plot_reward()
        self.plot_loss()
        self.env.close()

    def plot_reward(self):
        print(self.reward_plot)
        self.reward_plot = np.array(self.reward_plot)
        n_steps = 200*np.linspace(1,len(self.reward_plot),len(self.reward_plot))
        agent_0_rew = self.reward_plot[:,0]
        agent_1_rew = self.reward_plot[:,1]
        plt.plot(n_steps,agent_0_rew,label="agent0 reward")
        plt.plot(n_steps,agent_1_rew,label="agent1 reward")
        plt.legend()
        plt.xlabel("Number of Time Steps")
        plt.ylabel("Reward")
        plt.title("Reward vs. Time Steps")
        plt.savefig("Reward_plot_sleep_cnn.png")
        plt.show()
        

    def plot_loss(self):
        print(self.loss_plot)
        self.loss_plot = np.array(self.loss_plot)
        n_steps = 200*np.linspace(1,len(self.loss_plot),len(self.loss_plot))
        agent_0_loss = self.loss_plot[:,0]
        agent_1_loss = self.loss_plot[:,1]
        plt.plot(n_steps,agent_0_loss,label="agent0 loss")
        plt.plot(n_steps,agent_1_loss,label="agent1 loss")
        plt.legend()
        plt.xlabel("Number of Time Steps")
        plt.ylabel("Loss")
        plt.title("Loss vs. Time Steps")
        plt.savefig("Loss_plot_sleep_cnn.png")
        
        



    def perform_render(self):
        if self.show_render:
            self.add_overlay(const.GRID_TOPRIGHT, "Reset env; (current seed: {})".format(self.seed), "N - next / P - previous ")
            self.add_overlay(const.GRID_TOPRIGHT, "Reward", str(self.total_rew))
            if hasattr(self.env.unwrapped, "viewer_stats"):
                for k, v in self.env.unwrapped.viewer_stats.items():
                    self.add_overlay(const.GRID_TOPRIGHT, k, str(v))

            self.env.render()
           


    def reset_increment(self):
        self.total_rew_avg = (self.n_episodes * self.total_rew_avg + self.total_rew) / (self.n_episodes + 1)
        self.n_episodes += 1
        print(f"Reward: {self.total_rew} (rolling average: {self.total_rew_avg})")
        self.total_rew = 0.0
        #self.seed += 1
        self.env.seed(self.seed)

        #self.env.unwrapped.sim.set_state(self.saved_state)
        self.ob = self.env.reset()
        
        # for policy in self.policies:
        #     policy.reset()
        if hasattr(self.env, "reset_goal"):
            self.goal = self.env.reset_goal()
        self.update_sim(self.env.unwrapped.sim)


policy_types = {
    'q': lambda p, e, o, r, s, m: qn_trainer(p, e, o, r, s, m),
    'dqn': lambda p, e, o, r, s, m: dqn_trainer(p, e, o, r, s, m)
}


def qn_trainer(policies, env, ob, render_env, step, save_policy_model):
    if len(policies) == 1:
        action = policies[0].act(ob)
        last_act = action
        last_ob = ob
    else:
        ob = split_obs(ob, keepdims=False)
        ob_policy_idx = np.split(np.arange(len(ob)), len(policies))
        last_ob = ob
        last_ob_idx = ob_policy_idx
        actions = []
        for i, policy in enumerate(policies):
            inp = itemgetter(*ob_policy_idx[i])(ob)
            inp = listdict2dictnp([inp] if ob_policy_idx[i].shape[0] == 1 else inp)
            ac = policy.act(inp)
            actions.append(ac)
        action = listdict2dictnp(actions, keepdims=True)

    ob, rew, done, env_info = env.step(action)

    # Update policies
    if len(policies) == 1:
        policy.update(last_ob, last_act, ob, done)
    else:                    
        tmp_ob = splitobs(ob, keepdims=False)
        tmp_ob_policy_idx = np.split(np.arange(len(tmp_ob)), len(policies))

        for i, (a, r, policy) in enumerate(zip(actions, rew, policies)):
            last_inp = itemgetter(*last_ob_idx[i])(last_ob)
            last_inp = listdict2dictnp([last_inp] if last_ob_idx[i].shape[0] == 1 else last_inp)
            inp = itemgetter(*tmp_ob_policy_idx[i])(tmp_ob)
            inp = listdict2dictnp([inp] if tmp_ob_policy_idx[i].shape[0] == 1 else inp)
            policy.update(last_inp, r, a, inp, done)

    return ob, rew, done, env_info


def dqn_trainer(policies, env, ob, render_env, step, save_policy_model,model_type="cnn",env_name="baseline"):
    if len(policies) == 1:
        action, _ = policies[0].act(ob, agent_id=0, train=True)
        last_ob = ob
    else:
        # ob = splitobs(ob, keepdims=False)
        # ob_policy_idx = np.split(np.arange(len(ob)), len(policies))
        last_ob = ob
        actions = []
        for i, policy in enumerate(policies):
            
            # inp = itemgetter(*ob_policy_idx[i])(ob)
            # inp = listdict2dictnp([inp] if ob_policy_idx[i].shape[0] == 1 else inp)
            
            exisiting_model = None
            '''
            if (path.exists(f"models/dqn_{env_name}_{model_type}_agent{i}.pt")):
                existing_model = torch.load(f"models/dqn_{env_name}_{model_type}_agent{i}.pt")
            '''
            ac = policy.act(ob, agent_id=i, train=True,model=exisiting_model)
            
            actions.append(ac)
        
        action = listdict2dictnp(actions, keepdims=True)
        

    ob, rew, done, env_info = env.step(action)
    print("Reward from environment: ", rew)

    # Render now
    render_env()

    # Update policies and handle experience replay
    # Params (current observation, corresponding action, reward, next observation, finished)
    if len(policies) == 1:
        policies[0].update_replay_cache((last_ob, action, rew, ob, done))
        loss = [policies[0].train(step, agent_id=0)]
    else:                    
        # tmp_ob = splitobs(ob, keepdims=False)
        # tmp_ob_policy_idx = np.split(np.arange(len(ob)), len(policies))
        tmp_ob = ob
        loss = []
        for i, (a, r, policy) in enumerate(zip(actions, rew, policies)):
            # last_inp = itemgetter(*last_ob_idx[i])(last_ob)
            # last_inp = listdict2dictnp([last_inp] if last_ob_idx[i].shape[0] == 1 else last_inp)
            # inp = itemgetter(*tmp_ob_policy_idx[i])(tmp_ob)
            # inp = listdict2dictnp([inp] if tmp_ob_policy_idx[i].shape[0] == 1 else inp)

            policy.update_replay_cache((last_ob, a, r, tmp_ob, done), agent_id=i)
            l = policy.train(step, agent_id=i)
            loss.append(l)
    if save_policy_model:
        for i, policy in enumerate(policies):
            policy.save_policy(agent_id=i)

    return ob, rew, done, env_info,loss

