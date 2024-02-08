# coding: utf-8

# Standard imports

# External imports
import torch
import torch.nn as nn
from torchvision import models
from functools import reduce
import operator


class FeaturesMLP(nn.Module):
    def __init__(self, cfg, features_input_size, features_output_size):
        super().__init__()
        intermediate_layers = cfg["num_intermediate_layers"] *linear_relu(256,256)
        self.seq = nn.Sequential(
            nn.Linear(features_input_size, 256),
            nn.ReLU(inplace=True),
            *intermediate_layers,
            nn.Linear(256, features_output_size)
            )
        
    def forward(self, x):
        return self.seq(x)

def linear_relu(cin,cout):
    return [nn.Linear(cin,cout),nn.ReLU(inplace=True)]
    
class CNN(nn.Module):
    def __init__(self, cfg, image_input_size, output_size):
        super().__init__()
        def conv_relu_bn(cin, cout):
            return [
                nn.Conv2d(cin, cout, kernel_size=3, stride=1, padding=1),
                nn.ReLU(),
                nn.BatchNorm2d(cout),
            ]
        def conv_down(cin, cout):
            return [
                nn.Conv2d(cin, cout, kernel_size=2, stride=2, padding=0),
                nn.ReLU(),
                nn.BatchNorm2d(cout),
            ]
        
        layers = []
        cin = image_input_size[0]
        cout = 16
        for i in range(cfg["num_layers"]):
            layers.extend(conv_relu_bn(cin, cout))
            layers.extend(conv_relu_bn(cout, cout))
            layers.extend(conv_down(cout, 2 * cout))
            cin = 2 * cout
            cout = 2 * cout
        conv_model = nn.Sequential(*layers)

        # Compute the output size of the convolutional part
        probing_tensor = torch.zeros((1,) + image_input_size)
        out_cnn = conv_model(probing_tensor)  # B, K, H, W
        num_features = reduce(operator.mul, out_cnn.shape[1:], 1)
        out_layers = [nn.Flatten(start_dim=1), nn.Linear(num_features, output_size)]
        self.seq = nn.Sequential(conv_model, *out_layers)
           
    def forward(self, x):
        return self.seq(x)

class MyResNet18(nn.Module):
    def __init__(self, cfg ,image_input_size, output_size):
        super(MyResNet18, self).__init__()
        resnet = models.resnet18(weights = "IMAGENET1K_V1")
        
        modules = list(resnet.children())[:-2]
        resnet_model = nn.Sequential(*modules)

        probing_tensor = torch.zeros((1,) + image_input_size)
        out_cnn = resnet_model(probing_tensor)  # B, K, H, W
        num_features = reduce(operator.mul, out_cnn.shape[1:], 1)
        out_layers = [nn.Flatten(start_dim=1), nn.Linear(num_features, output_size)]
        self.seq = nn.Sequential(resnet_model, *out_layers)

    def forward(self, x):
        return self.seq(x)

class MyResNet34(nn.Module):
    def __init__(self, cfg, image_input_size,output_size):
        super(MyResNet34, self).__init__()
        resnet = models.resnet34(weights = "IMAGENET1K_V1")
        
        modules = list(resnet.children())[:-2]
        resnet_model = nn.Sequential(*modules)

        probing_tensor = torch.zeros((1,) + image_input_size)
        out_cnn = resnet_model(probing_tensor)  # B, K, H, W
        num_features = reduce(operator.mul, out_cnn.shape[1:], 1)
        out_layers = [nn.Flatten(start_dim=1), nn.Linear(num_features, output_size)]
        self.seq = nn.Sequential(resnet_model, *out_layers)

    def forward(self, x):
        return self.seq(x)
# multiple models https://discuss.pytorch.org/t/combining-trained-models-in-pytorch/28383
# eval() and train() do work recurcively !! :)
# gradient also does include child models. (except with .requires_grad=False)

class BiModel(nn.Module):
    def __init__(self, cfg, input_sizes, num_classes):
        super().__init__()
        # output sizes of cnn and features mlp can be chosen randomly, but by putting them at the number of classes / 4 makes both models try to extract inportant info withough behind to big
        image_input_size, features_input_size = input_sizes
        cnn_output_size = num_classes // 8
        features_output_size = num_classes // 8
        image_models_dict = {"cnn":CNN,"resnet34":MyResNet34,"resnet18":MyResNet18}
        image_model = image_models_dict[cfg["image_model"]["name"]]
        self.image_model = image_model(cfg["image_model"],image_input_size,cnn_output_size)
        self.features_model = FeaturesMLP(cfg["features_model"],features_input_size, features_output_size)
        self.seq = nn.Sequential(
            nn.Linear(cnn_output_size + features_output_size, num_classes//2), # 1226x2455
            nn.ReLU(),
            nn.Linear(num_classes//2, num_classes)
            )

    def forward(self, x):
        image, features = x
        cnn_output = self.image_model(image)
        mlp_output = self.features_model(features)

        # print(image.size()) # torch.Size([32, 3, 256, 256])
        # print(features.size()) # torch.Size([32, 29])

        concat = torch.cat((cnn_output, mlp_output), dim=1)
        # print(concat.size()) # torch.Size([32, 1226])
        return self.seq(concat)