import pandas as pd
from sklearn.naive_bayes import MultinomialNB, ComplementNB
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
import numpy as np
import os
np.random.seed(5)


def load_our_discord_dataset():
    """
    Loads the data from our custom Discord crypto scam dataset. We collected this ourselves by taking all screenshots
    from the "spam-report" channel of the r/CryptoCurrency Discord server, one of the largest crypto Discord servers.
    The "spam-report" channel is where users posts screenshots of scam messages they have received, so that the
    moderators can take action against them. To convert these to text, we passed each screenshot through Google's 
    Tesseract API for OCR. We collected all scam messages from the year 2022 (ignoring duplicates), for a total of 41 messages.

    For the ham (i.e., non-spam) messages, we used 41 random messages from the Crypto-Tweet GitHub repo (see subsequent
    function for more information). We use 41 spam and 41 ham messages in order to avoid class imbalance in the dataset.

    For the 41 spam messages, we use a 27/14 training/test split (which is a 65%-35% split). Ideally we would have more data,
    but it is difficult to collect a large dataset of this kind, from our position. Nevertheless, this classifier serves
    as a prototype of a pipeline that can generalize well to larger datasets to achieve stronger performance.
    """
    # Read in spam data from our collected Discord dataset
    train_data, test_data = [], []
    train_path = 'data/custom_discord_dataset/train'
    test_path = 'data/custom_discord_dataset/test'

    num_train, num_test = len(os.listdir(train_path)), len(os.listdir(test_path))
    for filename in os.listdir(train_path):
        with open(os.path.join(train_path, filename), 'r') as f:
            message_text = f.read().replace('\n', ' ')
            train_data.append(message_text)

    for filename in os.listdir(test_path):
        with open(os.path.join(test_path, filename), 'r') as f:
            message_text = f.read().replace('\n', ' ')
            test_data.append(message_text)

    # Read in Ham data from Crypto-Tweet GitHub repo, and randomly select messages to use
    ham_data = pd.read_csv("data/crypto_tweet/crypto_tweet_aggregateddata.csv")
    ham_data = ham_data[ham_data['Category'] == "Ham"]
    ham_data = ham_data.iloc[np.random.choice(np.arange(len(ham_data)), num_train+num_test), :]['Tweet'].tolist()

    train_data.extend(ham_data[:num_train])
    test_data.extend(ham_data[num_train:])

    X_train = pd.DataFrame({"Message": train_data})["Message"]
    X_test = pd.DataFrame({"Message": test_data})["Message"]
    Y_train = pd.Series(["Spam"]*num_train + ["Ham"]*num_train)
    Y_test = pd.Series(["Spam"]*num_test + ["Ham"]*num_test)

    return X_train, X_test, Y_train, Y_test


def load_crypto_tweet_dataset():
    """
    Load the crypto tweet dataset from https://github.com/Mottl/Crypto-Tweet
    and balance it so that it has balanced classes (for ham vs. spam)
    """
    # Read in dataset
    data = pd.read_csv("data/crypto_tweet/crypto_tweet_aggregateddata.csv")
    data = data[data['Category'].isin(['Spam', 'Ham'])] # Ignore "Listings"

    # Balance classes (to have half spam, half ham)
    spam_idxs = np.where(data['Category']=="Spam")[0]
    ham_idxs = np.where(data['Category'] == "Ham")[0]
    assert len(ham_idxs) > len(spam_idxs)
    ham_idxs_to_use = np.random.choice(ham_idxs, size=len(spam_idxs))
    idxs_to_keep = np.concatenate([ham_idxs_to_use, spam_idxs])
    data = data.iloc[idxs_to_keep, :]

    # Train/test split
    X_train, X_test, Y_train, Y_test = train_test_split(data['Tweet'],
                                                        data['Category'],
                                                        train_size=0.65,
                                                        random_state=0)

    return X_train, X_test, Y_train, Y_test


def train_model(X_train, Y_train):
    """
    Trains the Naive Bayes model on X_train and Y_train
    Uses TF-IDF when converting raw documents to a matrix of counts (so instead of raw counts, it downweights
    common words using TF-IDF). We also completely ignore stop words like "the", etc. since these are not very meaningful
    """
    # Vectorizer that creates the matrix of word counts (technically, TF-IDF features)
    vectorizer = TfidfVectorizer(stop_words="english").fit(X_train)
    # vectorizer = CountVectorizer(ngram_range=(1, 2), stop_words="english").fit(X_train)

    # Create Naive Bayes classifier
    model = MultinomialNB()
    # model = ComplementNB()

    # Train classifier
    model.fit(vectorizer.transform(X_train), Y_train)

    return vectorizer, model

def get_predictions(X_test, model, vectorizer, predict_proba=False):
    """
    Using the given model, gets spam vs. ham predictions on X_test
    Can either output the predicted class or the predicted probability
    """
    if predict_proba:
        predictions = model.predict_proba(vectorizer.transform(X_test))
    else:
        predictions = model.predict(vectorizer.transform(X_test))
    return predictions


if __name__ == "__main__":
    # Load both datasets
    X_train_ct, X_test_ct, Y_train_ct, Y_test_ct = load_crypto_tweet_dataset()
    X_train_disc, X_test_disc, Y_train_disc, Y_test_disc = load_our_discord_dataset()

    # Train both models
    vectorizer_ct, model_ct = train_model(X_train_ct, Y_train_ct)
    vectorizer_disc, model_disc = train_model(X_train_disc, Y_train_disc)

    # Evaluate Crypto-Tweets model on Crypto-Tweets test set
    preds_ct_on_ct = get_predictions(X_test_ct, model_ct, vectorizer_ct)
    print("Accuracy of CT model on CT test set:", (preds_ct_on_ct == Y_test_ct).mean())

    # Evaluate our Discord model on Discord test set
    preds_disc_on_disc = get_predictions(X_test_disc, model_disc, vectorizer_disc)
    print("Accuracy of Discord model on Discord test set:", (preds_disc_on_disc == Y_test_disc).mean())
    print()

    # Evaluate Crypto-Tweets model on Discord test set
    preds_ct_on_disc = get_predictions(X_test_disc, model_ct, vectorizer_ct)
    print("Accuracy of CT model on Discord test set:", (preds_ct_on_disc == Y_test_disc).mean())

    # Evaluate our Discord model on CT test set
    preds_disc_on_ct = get_predictions(X_test_ct, model_disc, vectorizer_disc)
    print("Accuracy of Discord model on CT test set:", (preds_disc_on_ct == Y_test_ct).mean())
    print()

    ########## Mixed dataset models
    # Create mixed datasets
    X_train_mixed = X_train_ct.append(X_train_disc)
    X_test_mixed = X_test_ct.append(X_test_disc)
    Y_train_mixed = Y_train_ct.append(Y_train_disc)
    Y_test_mixed = Y_test_ct.append(Y_test_disc)

    vectorizer_mixed, model_mixed = train_model(X_train_mixed, Y_train_mixed)

    # Evaluate mixed dataset model on Crypto-Tweets test set
    preds_mixed_on_ct = get_predictions(X_test_ct, model_mixed, vectorizer_mixed)
    print("Accuracy of mixed dataset model on CT test set:", (preds_mixed_on_ct == Y_test_ct).mean())

    # Evaluate mixed dataset model on Discord test set
    preds_mixed_on_disc = get_predictions(X_test_disc, model_mixed, vectorizer_mixed)
    print("Accuracy of mixed dataset model on Discord test set:", (preds_mixed_on_disc == Y_test_disc).mean())

    ########### Manual testing
    X_manual = pd.Series(["Congratulations! You have been selected for a free bitcoin giveaway!", 
                          "How are you?",
                          "I love this Discord channel! It has so many helpful people in it",
                          "Claim your free prize! Visit this link: https://bit.ly",
                          "Hello"])
    preds_manual = get_predictions(X_manual, model_mixed, vectorizer_mixed, predict_proba=True)
    np.set_printoptions(suppress=True)
    # print(preds_manual)
    
    
    
    # import ipdb; ipdb.set_trace()
