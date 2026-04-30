# Filename: ml_label_decoder_utils.py
# Purpose : Decode integer-encoded labels into human-readable malware family names and provide label utilities.

from sklearn.preprocessing import LabelEncoder

# === Primary decoder for classifier outputs ===
def decode_encoded_labels(y_true, y_pred, label_ids, label_encoder):
    """
    Convert encoded integer labels back to original class names.

    Returns:
        Tuple[List[str], List[str], List[str]]: Decoded y_true, y_pred, and label index list.
    """
    if label_encoder is None:
        return y_true, y_pred, label_ids

    try:
        decoded_true = label_encoder.inverse_transform(y_true)
        decoded_pred = label_encoder.inverse_transform(y_pred)
        decoded_ids = label_encoder.inverse_transform(label_ids)
        return decoded_true, decoded_pred, decoded_ids
    except Exception as e:
        raise RuntimeError(f"[LABEL DECODER] Failed to decode labels: {e}")


# === Utility: Get list of classes from a fitted encoder ===
def get_class_list(label_encoder):
    """
    Retrieve all class labels known to the encoder.

    Returns:
        List[str]: All known class labels in training set.
    """
    if label_encoder is None:
        raise ValueError("[LABEL DECODER] LabelEncoder instance is None.")
    return list(label_encoder.classes_)


# === Utility: Build lookup dictionary for index → label ===
def build_label_lookup(label_encoder):
    """
    Build index-to-label and label-to-index dictionaries.

    Returns:
        Tuple[dict, dict]: (index → label, label → index)
    """
    if label_encoder is None:
        raise ValueError("[LABEL DECODER] LabelEncoder instance is None.")

    label_list = list(label_encoder.classes_)
    index_to_label = {i: label for i, label in enumerate(label_list)}
    label_to_index = {label: i for i, label in enumerate(label_list)}
    return index_to_label, label_to_index


# === Utility: Convert a decoded label back to index ===
def encode_label(label, label_encoder):
    """
    Convert a class label to its corresponding integer index.

    Returns:
        int: Encoded label index
    """
    if label_encoder is None:
        raise ValueError("[LABEL DECODER] LabelEncoder instance is None.")
    return int(label_encoder.transform([label])[0])


# === Utility: Convert multiple labels to indices ===
def encode_labels(label_list, label_encoder):
    """
    Convert a list of labels to their encoded indices.

    Returns:
        List[int]: Encoded label indices
    """
    if label_encoder is None:
        raise ValueError("[LABEL DECODER] LabelEncoder instance is None.")
    return label_encoder.transform(label_list)
