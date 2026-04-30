import pandas as pd
from sklearn.decomposition import PCA
from scipy.stats import zscore
from utils import display_utils as du


def feature_correlation_summary(df: pd.DataFrame, threshold: float = 0.8, verbose: bool = True) -> pd.DataFrame:
    """Compute correlation matrix and print strong correlations."""
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.empty:
        du.print_warning("[PATTERN] No numeric columns to analyze.")
        return pd.DataFrame()
    corr = numeric_df.corr()
    if verbose:
        du.print_section("Feature Correlation Summary")
        strong_pairs = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                coeff = corr.iloc[i, j]
                if abs(coeff) >= threshold:
                    strong_pairs.append((cols[i], cols[j], coeff))
        if strong_pairs:
            du.print_info(f"Found {len(strong_pairs)} strongly correlated feature pairs (|r| >= {threshold}).")
            for a, b, c in strong_pairs:
                du.print_info(f"  {a} ↔ {b}: {c:.3f}")
        else:
            du.print_info("No feature pairs exceed correlation threshold.")
    return corr


def detect_outliers(df: pd.DataFrame, columns: list[str], z_thresh: float = 3.5, verbose: bool = True) -> pd.DataFrame:
    """Return rows where any specified column exceeds the z-score threshold."""
    if not columns:
        return pd.DataFrame()
    subset = df[columns].dropna()
    if subset.empty:
        return pd.DataFrame()
    z_scores = subset.apply(zscore)
    mask = (z_scores.abs() > z_thresh).any(axis=1)
    outliers = df.loc[mask]
    if verbose:
        du.print_info(f"[PATTERN] Detected {len(outliers)} potential outlier rows using z-threshold {z_thresh}.")
    return outliers


def compute_pca_features(df: pd.DataFrame, n_components: int = 2, verbose: bool = True) -> pd.DataFrame:
    """Append PCA component columns to the DataFrame."""
    numeric_df = df.select_dtypes(include="number").dropna()
    if numeric_df.empty:
        du.print_warning("[PATTERN] No numeric data available for PCA.")
        return df
    pca = PCA(n_components=n_components)
    components = pca.fit_transform(numeric_df)
    col_names = [f"PCA_{i+1}" for i in range(n_components)]
    pca_df = pd.DataFrame(components, columns=col_names, index=numeric_df.index)
    if verbose:
        ratios = ", ".join(f"{r:.3f}" for r in pca.explained_variance_ratio_[:n_components])
        du.print_info(f"[PATTERN] PCA explained variance ratios: {ratios}")
    return pd.concat([df, pca_df], axis=1)
