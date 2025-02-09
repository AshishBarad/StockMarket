import tensorflow as tf
import numpy as np

def predict_stock_trend(stock_data):
    try:
        # Load pre-trained model
        model = tf.keras.models.load_model("models/stock_model.h5")

        # Preprocess data for prediction
        data = stock_data['Close'].values
        data = np.reshape(data, (1, data.shape[0], 1))

        # Predict
        prediction = model.predict(data)
        return "Buy" if prediction[0][0] > 0 else "Sell"
    except Exception as e:
        raise Exception(f"Error predicting stock trend: {e}")