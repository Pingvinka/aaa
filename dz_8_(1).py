# -*- coding: utf-8 -*-
"""dz_8 (1).ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1RuB51nE4uXzW-SmphLYrm_uvM4JKhinP
"""

!pip install segmentation_models_pytorch

import os
from tqdm.notebook import tqdm
import gc
from torch.nn import Parameter
import torch.nn.functional as F
import torch.nn as nn
import math
import timm
import pandas as pl
import torch
import numpy as np
from torch.amp import GradScaler
import cv2
import random
from tqdm.notebook import tqdm
from torch.autograd import Variable
from skimage.metrics import structural_similarity as ssim
import pandas as pd
import segmentation_models_pytorch as smp

def seed_everything(seed):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

seed_everything(42)

from google.colab import drive
drive.mount('/content/drive')

!unzip /content/drive/MyDrive/ioai-2025-preparation-class-lesson-8-homework.zip

train_msk = np.load('/content/msk_array.npy')
train_images = sorted(os.listdir('/content/data/train/'))
test_images = sorted(os.listdir('/content/data/test/'))
test_msk = np.zeros((len(test_images), train_msk.shape[1], train_msk.shape[2]))

train_images = [f'/content/data/train/{path}' for path in train_images]
test_images = [f'/content/data/test/{path}' for path in test_images]
len(train_images)

import os
import numpy as np
import matplotlib.pyplot as plt
from tensorflow.keras.models import load_model

# Визуализация первых 10 изображений и масок
plt.figure(figsize=(20, 5))
for i in range(10):
    # Отображение изображения
    plt.subplot(2, 10, i + 1)
    img = plt.imread(train_images[i])
    plt.imshow(img)
    plt.title(f'Train Image {i+1}')
    plt.axis('off')

    # Отображение маски
    plt.subplot(2, 10, i + 11)
    plt.imshow(train_msk[i], cmap='gray')
    plt.title(f'Train Mask {i+1}')
    plt.axis('off')

plt.show()

from torchvision import transforms

class Dataset(torch.utils.data.Dataset):
    def __init__(self, path_image, msks, image_size=512):
        self.path_image = path_image
        self.msks = msks
        self.image_size = image_size

        # Нормализация для ImageNet
        self.mean = [0.485, 0.456, 0.406]  # Средние значения для ImageNet
        self.std = [0.229, 0.224, 0.225]    # Стандартные отклонения для ImageNet

        # Преобразования для изображений
        self.transform = transforms.Compose([
            transforms.ToTensor(),  # Конвертирует numpy array в тензор и нормализует в [0, 1]
            transforms.Normalize(mean=self.mean, std=self.std)  # Нормализация для ImageNet
        ])

    def __len__(self):
        return len(self.path_image)

    def __getitem__(self, i):
        # Загрузка изображения
        img = cv2.imread(self.path_image[i])
        if img is None:
            raise FileNotFoundError(f"Image at path {self.path_image[i]} not found or could not be loaded.")

        # Загрузка маски
        msk = self.msks[i]
        if len(msk.shape) == 2:
            msk = msk[:, :, None]
        elif msk.shape[2] != 1:
            msk = msk[:, :, 0:1]  # Берем только первый канал, если их несколько

        # Ресайз изображения и маски
        img = cv2.resize(img, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        msk = cv2.resize(msk, (self.image_size, self.image_size), interpolation=cv2.INTER_NEAREST)

        # Преобразование изображения
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # OpenCV загружает в BGR, преобразуем в RGB
        img = self.transform(img)  # Применяем нормализацию и преобразование в тензор

        # Преобразование маски
        msk = torch.from_numpy(msk.astype(np.float32))

        return img, msk

class Model(nn.Module):
    def __init__(self):
        super().__init__()


        self.unet = smp.Unet('efficientnet-b3',
                             encoder_weights='imagenet',
                             classes=1,
        )

    def forward(self, x):
        y = self.unet(x)
        return y

gc.collect()
torch.cuda.empty_cache()

batch_size = 4
valid_batch_size = 4
epochs = 10
lr = 0.0352
clip_grad_norm = 15.28

params_train = {'batch_size': batch_size, 'shuffle': True, 'num_workers': 2}
params_val = {'batch_size': batch_size, 'shuffle': False, 'num_workers': 2}

#train_loader = torch.utils.data.DataLoader(Dataset(train_images[:-70], train_msk[:-70]), **params_train)
#val_loader = torch.utils.data.DataLoader(Dataset(train_images[-70:], train_msk[-70:]), **params_val)

indices = np.arange(len(train_images))
np.random.shuffle(indices)  # Перемешиваем индексы

train_indices = indices[:-70]
val_indices = indices[-70:]

train_loader = torch.utils.data.DataLoader(Dataset([train_images[i] for i in train_indices], [train_msk[i] for i in train_indices]), **params_train)
val_loader = torch.utils.data.DataLoader(Dataset([train_images[i] for i in val_indices], [train_msk[i] for i in val_indices]), **params_val)

DEVICE='cuda'

from sklearn.metrics import f1_score
from torch.cuda.amp import GradScaler, autocast
from tqdm import tqdm

# Определение устройства
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Инициализация модели
model = Model().to(DEVICE)

# Вычисление количества шагов обучения
num_train_steps = int(len(train_loader) / batch_size * epochs)

# Функция потерь
loss_func = smp.losses.DiceLoss(mode="binary", smooth=1.)

# Инициализация GradScaler для mixed precision
scaler = GradScaler('cuda')

# Оптимизатор и планировщик
optimizer = torch.optim.AdamW(model.parameters(), lr)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, len(train_loader) * epochs, 1e-6)

# Функция валидации
def validate(model, val_loader, loss_func, device):
    model.eval()
    val_loss = 0
    with torch.no_grad():
        for img, target in val_loader:
            img = img.to(device)
            target = target.to(device)
            outputs = model(img)
            loss = loss_func(outputs, target)
            val_loss += loss.item()
    return val_loss / len(val_loader)

# Цикл обучения
for epoch in range(epochs):
    model.train()
    average_loss = 0
    tk0 = tqdm(enumerate(train_loader), total=len(train_loader))

    for batch_number, (img, target) in tk0:
        optimizer.zero_grad()
        img = img.to(DEVICE)
        target = target.to(DEVICE)

        # Mixed precision training
        with autocast():
            outputs = model(img)
            loss = loss_func(outputs, target)

        # Backpropagation с GradScaler
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip_grad_norm)
        scaler.step(optimizer)
        scaler.update()

        # Обновление планировщика
        scheduler.step()

        # Обновление среднего значения потерь
        average_loss += loss.cpu().detach().numpy()
        tk0.set_postfix(loss=average_loss / (batch_number + 1), lr=scheduler.get_last_lr()[0], stage="train", epoch=epoch)

    # Валидация
    val_loss = validate(model, val_loader, loss_func, DEVICE)
    print(f"Epoch {epoch + 1}/{epochs}, Train Loss: {average_loss / len(train_loader)}, Val Loss: {val_loss}")



params_val = {'batch_size': batch_size, 'shuffle': False, 'drop_last': False, 'num_workers': 2}
test_loader = torch.utils.data.DataLoader(Dataset(test_images, test_msk), **params_val)

preds = []
imgs_list = []
target_list = []
model.eval()
average_loss = 0
with torch.no_grad():
    for batch_number,  (img, target)  in enumerate(test_loader):
        img = img.to(DEVICE)
        target = target.to(DEVICE)

        with torch.amp.autocast('cuda'):
            outputs = model(img)

        preds += [outputs.sigmoid().to('cpu').numpy()]

preds = np.concatenate(preds)[:, 0, ...]

preds = (preds > 0.2).astype(np.uint8)

plt.figure(figsize=(20, 5))
for i in range(10):
    # Отображение тестового изображения
    plt.subplot(2, 10, i + 1)
    img = plt.imread(test_images[i])
    plt.imshow(img)
    plt.title(f'Test Image {i+1}')
    plt.axis('off')

    # Отображение предсказанной маски
    plt.subplot(2, 10, i + 11)
    plt.imshow(preds[i], cmap='gray')
    plt.title(f'Pred Mask {i+1}')
    plt.axis('off')

plt.show()

def rle_encode(x, fg_val=1):
    """
    Args:
        x:  numpy array of shape (height, width), 1 - mask, 0 - background
    Returns: run length encoding as list
    """

    dots = np.where(
        x.T.flatten() == fg_val)[0]  # .T sets Fortran order down-then-right
    run_lengths = []
    prev = -2
    for b in dots:
        if b > prev + 1:
            run_lengths.extend((b + 1, 0))
        run_lengths[-1] += 1
        prev = b
    return run_lengths

def list_to_string(x):
    """
    Converts list to a string representation
    Empty list returns '-'
    """
    if x: # non-empty list
        s = str(x).replace("[", "").replace("]", "").replace(",", "")
    else:
        s = '-'
    return s

true_list = [list_to_string(rle_encode(ans)) for ans in preds]

predict_df = pd.DataFrame()
predict_df['Id'] = [f'{x:03d}.jpg' for x in range(150)]
predict_df['Target'] = true_list
predict_df.to_csv('submission.csv', index = None)





"""#Модель с hf"""

from transformers import AutoImageProcessor, DetrForSegmentation
from transformers.image_transforms import rgb_to_id
import torch
from torch.utils.data import DataLoader
from transformers import AutoImageProcessor, DetrForSegmentation
from torch.optim import AdamW
from tqdm import tqdm

# Загрузка предварительно обученного процессора и модели
image_processor = AutoImageProcessor.from_pretrained("facebook/detr-resnet-50-panoptic")
model = DetrForSegmentation.from_pretrained("facebook/detr-resnet-50-panoptic")

import numpy as np
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from sklearn.model_selection import train_test_split
from transformers import AutoImageProcessor

# Загрузка данных
train_image_dir = "data/train"
test_image_dir = "data/test"
train_masks = np.load("msk_array.npy")  # Загрузка масок для обучения

# Список путей к изображениям
train_image_paths = [os.path.join(train_image_dir, img) for img in os.listdir(train_image_dir)]
test_image_paths = [os.path.join(test_image_dir, img) for img in os.listdir(test_image_dir)]

# Разделение данных на обучающую и валидационную выборки
train_image_paths, val_image_paths, train_masks, val_masks = train_test_split(
    train_image_paths, train_masks, test_size=0.2, random_state=42
)

# Пользовательский Dataset
class SegmentationDataset(Dataset):
    def __init__(self, image_paths, masks, processor, transform=None):
        self.image_paths = image_paths
        self.masks = masks
        self.processor = processor
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # Загрузка изображения
        image = Image.open(self.image_paths[idx]).convert("RGB")
        # Загрузка маски
        mask = self.masks[idx]

        # Предобработка изображения и маски
        inputs = self.processor(images=image, segmentation_maps=mask, return_tensors="pt")

        # Возвращаем pixel_values и labels
        return {
            "pixel_values": inputs["pixel_values"].squeeze(),  # Убираем batch dimension
            "labels": inputs["pixel_mask"].squeeze(),  # Убираем batch dimension
        }

# Загрузка предварительно обученного процессора
processor = AutoImageProcessor.from_pretrained("facebook/detr-resnet-50-panoptic")

# Создание Dataset
train_dataset = SegmentationDataset(train_image_paths, train_masks, processor)
val_dataset = SegmentationDataset(val_image_paths, val_masks, processor)
test_dataset = SegmentationDataset(test_image_paths, np.zeros((len(test_image_paths), 1, 1)), processor)  # Маски для теста не используются

# Создание DataLoader
train_dataloader = DataLoader(train_dataset, batch_size=4, shuffle=True)
val_dataloader = DataLoader(val_dataset, batch_size=4, shuffle=False)
test_dataloader = DataLoader(test_dataset, batch_size=4, shuffle=False)

# Проверка
print(f"Train batches: {len(train_dataloader)}")
print(f"Validation batches: {len(val_dataloader)}")
print(f"Test batches: {len(test_dataloader)}")



# Определение оптимизатора
optimizer = AdamW(model.parameters(), lr=5e-5)
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()
# Определение устройства (GPU или CPU)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# Цикл обучения
num_epochs = 3
for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    for batch in tqdm(train_dataloader, desc=f"Epoch {epoch + 1}/{num_epochs}"):
        # Перемещение данных на устройство
        pixel_values = batch['pixel_values'].to(device)
        labels = batch['labels'].to(device)

        # Обнуление градиентов
        optimizer.zero_grad()

        # Прямой проход
        with autocast():
          outputs = model(pixel_values=pixel_values, labels=labels)
          loss = outputs.loss

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        # Обратный проход и оптимизация
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    print(f"Epoch {epoch + 1}/{num_epochs}, Loss: {total_loss / len(train_dataloader)}")

    # Валидация
    model.eval()
    val_loss = 0
    with torch.no_grad():
        for batch in tqdm(val_dataloader, desc="Validation"):
            pixel_values = batch['pixel_values'].to(device)
            labels = batch['labels'].to(device)

            outputs = model(pixel_values=pixel_values, labels=labels)
            val_loss += outputs.loss.item()

    print(f"Validation Loss: {val_loss / len(val_dataloader)}")

# Сохранение модели
model.save_pretrained("path_to_save_model")
image_processor.save_pretrained("path_to_save_model")

"""#Yolo сегментация

"""

!pip install ultralytics

from ultralytics import YOLO

model = YOLO("yolo11n-seg.pt")

from PIL import Image

import os
import numpy as np
from PIL import Image
from sklearn.model_selection import train_test_split

# Пути к данным
train_image_dir = "data/train"
test_image_dir = "data/test"
train_masks = np.load("msk_array.npy")  # Загрузка масок

# Создание структуры папок
os.makedirs("dataset/images/train", exist_ok=True)
os.makedirs("dataset/images/val", exist_ok=True)
os.makedirs("dataset/labels/train", exist_ok=True)
os.makedirs("dataset/labels/val", exist_ok=True)

# Функция для преобразования масок в YOLO формат
def mask_to_yolo_format(mask, class_id):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    yolo_annotations = []
    for contour in contours:
        contour = contour.squeeze()
        contour = contour / np.array([mask.shape[1], mask.shape[0]])  # Нормализация
        contour = contour.flatten().tolist()
        yolo_annotations.append([class_id] + contour)
    return yolo_annotations

# Разделение данных на train и val
train_image_paths = [os.path.join(train_image_dir, img) for img in os.listdir(train_image_dir)]
train_image_paths, val_image_paths, train_masks, val_masks = train_test_split(
    train_image_paths, train_masks, test_size=0.2, random_state=42
)

# Сохранение изображений и аннотаций
for image_paths, masks, split in zip(
    [train_image_paths, val_image_paths], [train_masks, val_masks], ["train", "val"]
):
    for image_path, mask in zip(image_paths, masks):
        # Копирование изображений
        image_name = os.path.basename(image_path)
        new_image_path = os.path.join("dataset/images", split, image_name)
        os.rename(image_path, new_image_path)

        # Преобразование масок и сохранение аннотаций
        yolo_annotations = mask_to_yolo_format(mask, class_id=0)  # class_id=0 для одного класса
        label_path = os.path.join("dataset/labels", split, os.path.splitext(image_name)[0] + ".txt")
        with open(label_path, "w") as f:
            for ann in yolo_annotations:
                f.write(" ".join(map(str, ann)) + "\n")

data_yaml = f"""
path: /content/dataset
train: images/train
val: images/val
test: images/test

names:
  0: object
"""
with open(os.path.join('/content/data', 'data.yaml'), 'w') as f:
    f.write(data_yaml)

torch.use_deterministic_algorithms(False)

results = model.train(
    data='/content/data/data.yaml',  # Путь к конфигурационному файлу
    epochs=5,        # Количество эпох
    imgsz=256,         # Размер изображения
    batch=16,
    device='0'
)

model = YOLO("runs/segment/train/weights/best.pt")

# Предикт на тестовых данных
results = model.predict(
    task = 'segment',
    source="/content/data/test",
    save=True,  # Сохранить результаты
    conf=0.01,  # Порог уверенности
    show_labels=True,
    show_conf=True,
)

