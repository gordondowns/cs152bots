The Naive Bayes classifier (for crypto scam classification) is trained in naive_bayes_classifier.py

Currently, the model trained on the Discord dataset that we collected is saved in models/trained_on_discord.
To use this model and predict on your own data, do the following:

(You will notice that the performance is not very good, due to the small size of the dataset. This
is a prototype of the full pipeline that would ideally be run on thousands/millions of training examples.)

```
import pickle
import pandas as pd
from naive_bayes_classifier import get_predictions

# Load model and vectorizer that were trained on our Discord dataset
vectorizer_disc = pickle.load(open("models/trained_on_discord/vectorizer_disc.pickle", "rb"))
model_disc = pickle.load(open("models/trained_on_discord/model_disc.pickle", "rb"))

# Manually create some examples to run on
X_manual = pd.Series(["Congratulations! You have been selected for a free bitcoin giveaway!", 
                      "Bitcoin is pretty interesting"])

# Get predicted probabilities of ham vs. spam
preds = get_predictions(X_manual, model_disc, vectorizer_disc, predict_proba=True)
```