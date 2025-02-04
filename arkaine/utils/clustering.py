from collections import Counter
from typing import List

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def find_optimal_cluster_representative(vectors: List[List[float]]) -> int:
    """
    Find the index of the vector that best represents the most common cluster.

    This function performs the following steps:
    1. Determines the optimal number of clusters using silhouette scores.
    2. Performs K-means clustering with the optimal number of clusters.
    3. Identifies the most common cluster.
    4. Finds the vector closest to the center of the most common cluster.

    Args:
    vectors (List[List[float]]): A list of vectors, where each vector is a
        list of floats.

    Returns:
    int: The index of the vector closest to the center of the most common
        cluster.

    Raises:
    ValueError: If the input list is empty or contains fewer than 2 vectors.
    """

    if not vectors or len(vectors) < 2:
        raise ValueError("Input must contain at least 2 vectors")

    vectors_array = np.array(vectors)

    # Main process
    optimal_k = determine_optimal_clusters(vectors_array)
    kmeans_model = perform_clustering(vectors_array, optimal_k)
    most_common_cluster = find_most_common_cluster(kmeans_model.labels_)
    most_common_center = kmeans_model.cluster_centers_[most_common_cluster]
    closest_index = find_closest_vector_index(vectors_array, most_common_center)

    return closest_index


def determine_optimal_clusters(data: np.ndarray, max_clusters: int = 10) -> int:
    """
    Determine the optimal number of clusters using silhouette scores.

    Args:
    data (np.ndarray): The data to cluster.
    max_clusters (int): The maximum number of clusters to consider.

    Returns:
    int: The optimal number of clusters.
    """
    max_clusters = min(max_clusters, len(data) - 1)
    silhouette_scores = []

    for k in range(2, max_clusters + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        score = silhouette_score(data, labels)
        silhouette_scores.append(score)

    return silhouette_scores.index(max(silhouette_scores)) + 2


def perform_clustering(data: np.ndarray, n_clusters: int) -> KMeans:
    """
    Perform K-means clustering on the data.

    Args:
    data (np.ndarray): The data to cluster.
    n_clusters (int): The number of clusters to use.

    Returns:
    KMeans: The fitted KMeans model.
    """
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(data)
    return kmeans


def find_most_common_cluster(labels: np.ndarray) -> int:
    """
    Find the most common cluster label.

    Args:
    labels (np.ndarray): The cluster labels.

    Returns:
    int: The label of the most common cluster.
    """
    cluster_counts = Counter(labels)
    return cluster_counts.most_common(1)[0][0]


def find_closest_vector_index(data: np.ndarray, point: np.ndarray) -> int:
    """
    Find the index of the vector in data closest to the given point.

    Args:
    data (np.ndarray): The data array.
    point (np.ndarray): The point to compare against.

    Returns:
    int: The index of the closest vector.
    """
    distances = np.linalg.norm(data - point, axis=1)
    return np.argmin(distances)
