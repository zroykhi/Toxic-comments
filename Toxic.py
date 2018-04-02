import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import torch.utils.data
from keras.preprocessing import text, sequence
from sklearn.metrics import roc_auc_score
from torch import nn, optim
from torch.autograd import Variable

from skorch.net import NeuralNetClassifier
from sklearn.model_selection import GridSearchCV


TEST = True
#TEST = False
batch_size = 25

max_features = 20000
maxlen = 100
embed_size = 100
# train the training data n times
epochs = 1

train = pd.read_csv("./data/train_small.csv")
test = pd.read_csv("./data/test_small.csv")
train = train.sample(frac=1)

sentences_train = train["comment_text"].fillna("CVxTz").values
list_classes = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]
y = train[list_classes].values
sentences_test = test["comment_text"].fillna("CVxTz").values

tokenizer = text.Tokenizer(num_words=max_features)
# fit_on_text(texts): use texts(list) to generate token dictionary
tokenizer.fit_on_texts(list(sentences_train))
word_index = tokenizer.word_index # index of words

tokenized_train = tokenizer.texts_to_sequences(sentences_train) # sequencing words
tokenized_test = tokenizer.texts_to_sequences(sentences_test)
# if the number of words is below maxlen=100, fill the rest with 0(from left)
X_train = sequence.pad_sequences(tokenized_train, maxlen=maxlen)
X_test = sequence.pad_sequences(tokenized_test, maxlen=maxlen)
# convert X and y to torch Dataset format
train_set = torch.utils.data.TensorDataset(torch.from_numpy(X_train).long(), torch.from_numpy(y).float())
# batch_size: number of example to train each time
train_loader = torch.utils.data.DataLoader(train_set, batch_size=batch_size)
test_loader = torch.utils.data.DataLoader(torch.from_numpy(X_test).long(), batch_size=1024)

# pretrained embeddings
# emb_file = "./pretrained/glove.twitter.27B.200d.txt"
# emb_file = "embeded_test_sentences.txt"
emb_file = './data/pretraind-glove.txt'

embeddings_index = {}

with open(emb_file) as f:
    for line in f:
        values = line.split()
        word = values[0]
        coefs = np.asarray(values[1:], dtype='float32')
        embeddings_index[word] = coefs

embedding_matrix = np.zeros((len(word_index) + 1, embed_size))

for word, i in word_index.items():
    embedding_vector = embeddings_index.get(word)
    if embedding_vector is not None:
        # words not found in embedding index will be all-zeros.
        embedding_matrix[i] = embedding_vector


class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        p = .1 # drop rate
        self.embeddings = nn.Embedding(num_embeddings=max_features, embedding_dim=embed_size)
        self.embeddings.weight.data = torch.Tensor(embedding_matrix)
        # data structure (batch, time_step, input), if batch is in the first position, batch_first=True, otherwise false
        # input_siez=embed_size: number of input, hidden_size=50: number of neurons each layer, num_layers=1: number of layer
        self.lstm = nn.LSTM(embed_size, 50, 1, batch_first=True, bidirectional=True)
        self.hidden = (
            Variable(torch.zeros(2, 1, 50)),
            Variable(torch.zeros(2, 1, 50))) # hidden state

        self.max_pool = nn.MaxPool1d(100)
        self.dropout = nn.Dropout(p=p)
        self.lin_1 = nn.Linear(100, 50) # fully connected layer
        self.relu = nn.ReLU() # activatoin function
        self.dropout_2 = nn.Dropout(p=p)
        self.lin_2 = nn.Linear(50, 6) # fully connected layer
        self.sig = nn.Sigmoid()

    def forward(self, x):
        x = self.embeddings(x)
        # x, self.hidden = self.lstm(x) # every time it will return a hidden state, we use it together with next data to generate new output
        x, (h_n, h_c) = self.lstm(x) # myself
        x = self.max_pool(x) # need to select only the last output to pool?
        x = x.view(x.size(0), -1) # unscroll data,x.size(0) not change, the rest turns into one dimmension
        x = self.dropout(x)
        x = self.lin_1(x) # fully connected layer
        x = self.relu(x) # apply activation function 
        x = self.dropout_2(x)
        x = self.lin_2(x) # fully connected layer
        return self.sig(x)

def train():
    learnin1g_rate = 1e-4
    # intialize the optimizer, use optimizer to accelorate learnnig process
    # there are different optimizers: SGD, Adagrad, Adadelta, Adam, Adamax, Nadam
    optimizer = optim.Adam(model.parameters(), lr=learnin1g_rate)
    # start model training
    for epoch in range(epochs):
        model.train()
        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = Variable(data), Variable(target)
            y_pred = model(data)
            loss = F.binary_cross_entropy(y_pred, target) # binary cross entropy loss
            print(loss.data[0])
            model.zero_grad() # orginal, clear gradients for this training step
            # optimizer.zero_grad() # myself, clear gradients for this training step
            loss.backward()
            optimizer.step() # apply gradients

#        model.eval()


# create Net for model
model = Net()
print(model)
# start train()
train()
model.eval()
preds = []

print("train complete")

if TEST:
    print("roc auc score")
    for batch_idx, (data, _) in enumerate(train_loader):
        data = Variable(data, volatile=True)

        output = model(data)
        pred = output.data
        preds.append(pred.numpy())

    y_test = np.concatenate(preds, axis=0)
    print(roc_auc_score(y, y_test))
else:
    for data in test_loader:
        data = Variable(data, volatile=True)
        output = model(data)
        pred = output.data
        preds.append(pred.numpy())

    y_test = np.concatenate(preds, axis=0)
    sample_submission = pd.read_csv("./data/sample_submission_small.csv")
    sample_submission[list_classes] = y_test
    sample_submission.to_csv("./data/submission.csv", index=False)
