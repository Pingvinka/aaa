# -*- coding: utf-8 -*-
"""dz_7.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1wet06a0Uoz8wquG9c1Ql_Tykcwhy3hzK

# Fine-tuning VGG Network.

In this hometask you'll need to fine-tune VGG network for dogs classification (the same dataset as in practical seminar).

## Loading the data
"""

# this cell downloads zip archive with data
! wget "https://www.dropbox.com/s/r11z0ugf2mezxvi/dogs.zip?dl=0" -O dogs.zip

# this cell extract the archive. You'll now have "dogs" folder in colab
! unzip -qq dogs.zip

import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import transforms, datasets, models
from sklearn.model_selection import train_test_split
from torch.nn import functional as F
from tqdm.notebook import tqdm
from torch.utils.data import Dataset, DataLoader

from matplotlib import pyplot as plt
from IPython.display import clear_output
from sklearn.metrics import accuracy_score
import random
from torch.optim.lr_scheduler import StepLR

seed = 42

random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

"""## Task 1

Your task is to fine-tune [VGG11 ](https://pytorch.org/vision/0.20/models/generated/torchvision.models.vgg11.html) network from torchvision for the task of dogs breed classification. Your task is to tune the model so that it has the best test accuracy possible. You are not allowed to use any other pretrained model except this and any other data except given.

What you can do:
- **Preprocess and augment data**. Note the following: there is a difference between ordinary data preprocessing (as we did in the practical session) and augmentation. Preprocessing usually refers to the way all the data (train and test) is processed before feeding into the network; augmentation is a technique used to populate training set of samples. Augmentation should only be used on training data, but not on validation and test data. You can read more about augmentation [here](https://d2l.ai/chapter_computer-vision/image-augmentation.html). Also think about what kind of image augmentations are suitable for the given task, e.g. would that be beneficial to flip images vertically in our case?
- **Change/remove/add layers to the network**. You can change layers of the pre-trained VGG11. Note, however, that newly added layers should not be pre-trained. You are allowed to add any layers, e.g. conv, fc, dropout, batchnorm
- **Tune hyperparameters**, e.g. batch size, learning rate, etc.

If X is your score on test set, them your task score is calculated as follows: min(0.95, (X-0.75))*5

#Датасееееет
"""

'''
dataset = datasets.ImageFolder(root='/content/dogs/train', transform=transforms.Compose([transforms.ToTensor(),  transforms.Resize((224, 224))]))
dataloader = DataLoader(dataset, batch_size=32)

mean = torch.zeros(3)
std = torch.zeros(3)
for images, _ in dataloader:
    mean += images.mean((0, 2, 3))
    std += images.std((0, 2, 3))

mean /= len(dataloader)
std /= len(dataloader)

print("Mean:", mean)
print("Std:", std)
'''

train_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(256),
    transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.1, contrast=0.08, saturation=0.1, hue=0.05),
    transforms.RandomRotation(15),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5255, 0.4894, 0.4217], std=[0.2651, 0.2608, 0.2681])
])

test_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(256),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.4623, 0.4075, 0.3524], std=[0.2453, 0.2229, 0.2549])
])

train_data = datasets.ImageFolder(root='/content/dogs/train', transform=train_transform)
val_data = datasets.ImageFolder(root='/content/dogs/valid', transform=test_transform)
test_data = datasets.ImageFolder(root='/content/dogs/test', transform=test_transform)

len(train_data.classes) #Количество классов:

train_loader = DataLoader(train_data, batch_size=16, shuffle=True) #пробовала разный размер батча: 64, 32, 16. Лучшим 16 оказался
val_loader = DataLoader(val_data, batch_size=16, shuffle=False)
test_loader = DataLoader(test_data, batch_size=16, shuffle=False)

f, axes= plt.subplots(1, 8, figsize=(30,5))

for i, axis in enumerate(axes):
    img, label = train_data[i]
    img = np.transpose(img, (1, 2, 0))
    axes[i].imshow(img)
plt.show()

"""#Моделька и обучение туда-сюда"""

from torchvision import models

model = models.vgg11(weights='IMAGENET1K_V1')
model

'''
model.features = nn.Sequential(
    *list(model.features.children()),  # Сохраняем оригинальные слои VGG11
    nn.Conv2d(512, 512, kernel_size=3, padding=1),  # Добавляем новый сверточный слой, чтоб моделька лучше выделала признаки (ммм, ну, точнее, выделяла более сложные признаки, чем раньше)
    nn.ReLU(inplace=True),
    nn.MaxPool2d(kernel_size=2, stride=2)
)
'''
for param in model.features.parameters():
    param.requires_grad = False

# Переделываем classifier (полносвязные слои)
model.classifier = nn.Sequential(
    nn.Linear(512 * 7 * 7, 3072),
    nn.BatchNorm1d(3072),
    nn.ReLU(inplace=True),
    nn.Dropout(0.7),
    nn.Linear(3072, 512),
    nn.BatchNorm1d(512),
    nn.ReLU(inplace=True),
    nn.Dropout(0.5),
    nn.Linear(512, 70)
    #nn.LeakyReLU(),
    #nn.Linear(70, 70)
)

print(model)

'''
model.features = nn.Sequential(
    *list(model.features.children()),  # Сохраняем оригинальные слои VGG11
    nn.Conv2d(512, 512, kernel_size=3, padding=1),  # Добавляем новый сверточный слой, чтоб моделька лучше выделала признаки (ммм, ну, точнее, выделяла более сложные признаки, чем раньше)
    nn.ReLU(inplace=True),
    nn.MaxPool2d(kernel_size=2, stride=2)
)
'''

for param in model.features.parameters():
    param.requires_grad = False

# Переделываем classifier (полносвязные слои)
model.classifier = nn.Sequential(
    nn.Linear(512 * 7 * 7, 3072),
    nn.BatchNorm1d(3072),
    nn.ReLU(inplace=True),
    nn.Dropout(0.6),
    nn.Linear(3072, 512),
    nn.BatchNorm1d(512),
    nn.ReLU(inplace=True),
    nn.Dropout(0.6),
    nn.Linear(512, 70)
    #nn.LeakyReLU(),
    #nn.Linear(70, 70)
)

device = 'cuda' if torch.cuda.is_available() else 'cpu'

optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()
train_losses = []
val_losses = []
train_acc_scores = []
val_acc_scores = []

best_val_acc = 0.0
best_model_path = 'best_model.pth'
model = model.to(device)
num_epochs = 16

scheduler = StepLR(optimizer, step_size=4, gamma=0.2)  #Каждые 4 эпохи лр уменьшается в 5 раз

for epoch in range(num_epochs):
    model.train()
    running_loss = 0.0
    train_true = []
    train_pred = []

    for inputs, labels in tqdm(train_loader):
        inputs, labels = inputs.to(device), labels.to(device)



        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        running_loss += loss.item()

        preds = torch.argmax(outputs, dim=1)
        train_true.extend(labels.cpu().numpy())
        train_pred.extend(preds.cpu().numpy())

    train_acc = accuracy_score(train_true, train_pred)
    train_losses.append(running_loss / len(train_loader))
    train_acc_scores.append(train_acc)

    scheduler.step()
    model.eval()
    val_running_loss = 0.0
    val_true = []
    val_pred = []

    with torch.no_grad():
        for inputs, labels in tqdm(val_loader):
            inputs, labels = inputs.to(device), labels.to(device)

            outputs = model(inputs)
            loss = criterion(outputs, labels)

            val_running_loss += loss.item()

            preds = torch.argmax(outputs, dim=1)
            val_true.extend(labels.cpu().numpy())
            val_pred.extend(preds.cpu().numpy())

    val_acc = accuracy_score(val_true, val_pred)
    val_losses.append(val_running_loss / len(val_loader))
    val_acc_scores.append(val_acc)

    if val_acc > best_val_acc:
        best_val_acc = val_acc
        torch.save(model.state_dict(), best_model_path)
        print(f'New best model saved with accuracy: {best_val_acc:.4f}')

    print(f'Epoch [{epoch+1}/{num_epochs}], '
          f'Train Loss: {train_losses[-1]:.4f}, Train accuracy: {train_acc:.4f}, '
          f'Val Loss: {val_losses[-1]:.4f}, Val accuracy: {val_acc:.4f}')

def model_plot(train_losses, val_losses):
  plt.figure(figsize=(14, 5))
  plt.subplot(1, 2, 1)
  plt.plot(train_losses, label='Train Loss')
  plt.plot(val_losses, label='Validation Loss')
  plt.title('Loss')
  plt.xlabel('Epoch')
  plt.ylabel('Loss')
  plt.legend()

  plt.show()

model_plot(train_losses, val_losses)

def evaluate(model, loader, criterion, device):
    '''
    args:
        model - our neural network model
        loader — structure which yields batches of test data
        criterion - loss function from `torch.nn` module
    '''
    model.to(device)
    model.eval()
    losses = []
    y_pred_list = []
    y_true_list = []

    for X_batch, y_batch in loader:
        with torch.no_grad():
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            y_pred = model(X_batch)
            loss = criterion(y_pred, y_batch)
            losses.append(loss.item())

        y_pred = torch.argmax(y_pred, dim=1).tolist()
        y_pred_list.extend(y_pred)
        y_true_list.extend(y_batch.tolist())
    accuracy = accuracy_score(y_true_list, y_pred_list)

    return np.mean(losses), accuracy

model.load_state_dict(torch.load('/content/best_model.pth'))

evaluate(model, test_loader, criterion, device)