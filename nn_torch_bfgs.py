import sys
import numpy as np
import torch
import torch.nn as nn
from torch.nn import init
from torch.nn import Tanh, Softplus,LeakyReLU
from torch.nn.init import xavier_uniform_
import copy
from collections import OrderedDict
import time
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from amp.utilities import Logger

class Dense(nn.Linear):
    """Constructs and applies a dense layer with an activation function (when
    available) y=activation(Ax+b)

    Arguments:
        input_size (int): number of input features
        output_size (int): number of output features
        bias (bool): True to include bias at each neuron. False otherwise
        (Default: True)
        activation (callable): activation function to be utilized (Default:None)

    (Simplified version of SchNet Pack's implementation')

    """

    def __init__(self,input_size,output_size, bias=True,activation=None):
        self.activation=activation
        super(Dense,self).__init__(input_size,output_size,bias)

    def reset_parameters(self):
        # init.constant_(self.weight,.05)
        # init.constant_(self.bias,-1)

        super(Dense,self).reset_parameters()
        # init.constant_(self.bias,0)

    def forward(self,inputs):
        neuron_output=super(Dense,self).forward(inputs)
        if self.activation:
            neuron_output=self.activation()(neuron_output)
        return neuron_output

class MLP(nn.Module):
    """Constructs a fully connected neural network model to be utilized for
    each element type'''

    Arguments:
        n_input_nodes: Number of input nodes (Default=20 using BP SF)
        n_output_nodes: Number of output nodes (Default=1)
        n_layers: Total number of layers in the neural network
        n_hidden_size: Number of neurons within each hidden layer
        activation: Activation function to be utilized. (Default=Tanh())

    (Simplified version of SchNet Pack's implementation')

    """

    def __init__(self,n_input_nodes=20,n_output_nodes=1,n_layers=3,n_hidden_size=5,activation=Tanh):
        super(MLP,self).__init__()
        #if n_hidden_size is None:
            #implement pyramid neuron structure across each layer
        if type(n_hidden_size) is int:
            n_hidden_size=[n_hidden_size] * (n_layers-1)
        self.n_neurons=[n_input_nodes]+n_hidden_size+[n_output_nodes]
        self.activation=activation
        # HiddenLayer1=Dense(20,5,activation=activation)
        # HiddenLayer2=Dense(5,5,activation=activation)
        # OutputLayer3=Dense(5,1,activation=None)
        layers=[Dense(self.n_neurons[i],self.n_neurons[i+1],activation=activation) for i in range(n_layers-1)]
        layers.append(Dense(self.n_neurons[-2],self.n_neurons[-1],activation=None))
        self.model_net=nn.Sequential(*layers)
        # self.model_net=nn.Sequential(HiddenLayer1,HiddenLayer2,OutputLayer3)

    def forward(self, inputs):
        """Feeds data forward in the neural network

        Arguments:
            inputs (torch.Tensor): NN inputs
        """

        return self.model_net(inputs)

class FullNN(nn.Module):
    '''Combines element specific NNs into a model to predict energy of a given
    structure

    '''
    def __init__(self,unique_atoms,batch_size):
        log=Logger('benchmark_results/results-log.txt')

        super(FullNN,self).__init__()
        self.unique_atoms=unique_atoms
        self.batch_size=batch_size
        n_unique_atoms=len(unique_atoms)
        elementwise_models=nn.ModuleList()
        for n_models in range(n_unique_atoms):
            elementwise_models.append(MLP())
        self.elementwise_models=elementwise_models
        log('Activation Function = %s'%elementwise_models[0].activation)

    def forward(self,data):
        energy_pred=torch.zeros(self.batch_size,1)
        energy_pred=energy_pred.to(device)
        for index,element in enumerate(self.unique_atoms):
            model_inputs=data[element][0]
            contribution_index=data[element][1]
            atomwise_outputs=self.elementwise_models[index].forward(model_inputs)
            for cindex,atom_output in enumerate(atomwise_outputs):
                energy_pred[contribution_index[cindex]]+=atom_output
        return energy_pred

def feature_scaling(data):
    data_max=max(data)
    data_min=min(data)
    scale=[]
    for index,value in enumerate(data):
        scale.append((value-data_min)/(data_max-data_min))
    return torch.stack(scale)

def plot_grad_flow(named_parameters):
    '''Plots the gradients flowing through different layers in the net during training.
    Can be used for checking for possible gradient vanishing / exploding problems.

    Usage: Plug this function in Trainer class after loss.backwards() as
    "plot_grad_flow(self.model.named_parameters())" to visualize the gradient flow'''
    ave_grads = []
    max_grads= []
    layers = []
    for n, p in named_parameters:
        if(p.requires_grad) and ("bias" not in n):
            layers.append(n)
            ave_grads.append(p.grad.abs().mean())
            max_grads.append(p.grad.abs().max())
    plt.bar(np.arange(len(max_grads)), max_grads, alpha=0.1, lw=1, color="c")
    plt.bar(np.arange(len(max_grads)), ave_grads, alpha=0.1, lw=1, color="b")
    plt.hlines(0, 0, len(ave_grads)+1, lw=2, color="k" )
    plt.xticks(range(0,len(ave_grads), 1), layers, rotation="vertical")
    plt.xlim(left=0, right=len(ave_grads))
    plt.ylim(bottom = -0.001, top=0.02) # zoom in on the lower gradient regions
    plt.xlabel("Layers")
    plt.ylabel("average gradient")
    plt.title("Gradient flow")
    plt.grid(True)
    plt.legend([Line2D([0], [0], color="c", lw=4),
                Line2D([0], [0], color="b",
                    lw=4),Line2D([0],[0],color="k",lw=4)],['max-gradient','mean-gradient','zero-gradient'])

def train_model(model,unique_atoms,dataset_size,criterion,optimizer,atoms_dataloader,num_epochs):
    log=Logger('benchmark_results/results-log.txt')
    log_epoch=Logger('benchmark_results/epoch-log.txt')
    log('Model: %s'%model)

    since = time.time()
    log_epoch('-'*50)
    print('Training Initiated!')
    log_epoch('%s Training Initiated!'%time.asctime())
    log_epoch('')

    best_model_wts=copy.deepcopy(model.state_dict())
    best_loss=100000000

    plot_epoch_x=list(range(1,num_epochs+1))
    plot_loss_y=[]

    for epoch in range(num_epochs):
        log_epoch('{} Epoch {}/{}'.format(time.asctime(),epoch+1,num_epochs))
        log_epoch('-'*30)

        MSE=0.0

        for data_sample in atoms_dataloader:
            # print data_sample
            input_data=data_sample[0]
            target=data_sample[1]
            batch_size=len(target)
            # target=feature_scaling(target)

            #Send inputs and labels to the corresponding device (cpu or gpu)
            for element in unique_atoms:
                input_data[element][0]=input_data[element][0].to(device)
            target=target.to(device)

            def closure():
                #zero the parameter gradients
                optimizer.zero_grad()
                #forward
                output=model(input_data)
                loss=criterion(output,target)
                #backward + optimize only if in training phase
                loss.backward()
                # plot_grad_flow(model.named_parameters())
                return loss

            optimizer.step(closure)

            with torch.no_grad():
                pred=model(input_data)
                loss=criterion(pred,target)
                MSE+=loss.item()*batch_size
                sys.exit()

        MSE=MSE/dataset_size
        RMSE=np.sqrt(MSE)
        epoch_loss=RMSE
        print epoch_loss
        plot_loss_y.append(np.log10(RMSE))

        log_epoch('{} Loss: {:.4f}'.format(time.asctime(),epoch_loss))

        if epoch_loss<best_loss:
            best_loss=epoch_loss
            best_model_wts=copy.deepcopy(model.state_dict())
        log_epoch('')

    time_elapsed=time.time()-since
    print('Training complete in {:.0f}m {:.0f}s'.format
            (time_elapsed//60,time_elapsed % 60))

    log('')
    log('Training complete in {:.0f}m {:.0f}s'.format
                (time_elapsed//60,time_elapsed % 60))

    log('Best training loss: {:4f}'.format(best_loss))

    log('')

    plt.title('RMSE vs. Epoch')
    plt.xlabel('Epoch #')
    plt.ylabel('log(RMSE)')
    plt.plot(plot_epoch_x,plot_loss_y,label='train')
    plt.legend()
    plt.show()

    model.load_state_dict(best_model_wts)
    return model

device=torch.device("cuda:0" if torch.cuda.is_available() else "cpu")