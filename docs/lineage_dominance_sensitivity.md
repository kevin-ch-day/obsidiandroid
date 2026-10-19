# Family and lineage dominance sensitivity

`obsidiandroid.modeling.lineage_training_weights.lineage_class_weights` supports
an explicit research sensitivity analysis. It does not change normal pipeline
defaults, cohort admission, labels, split policy, or permission eligibility.

Pass **only the training partition**, indexed by unique sample IDs, with
`recorded_family` and `lineage_component` columns. Each family receives equal
total weight; each lineage within that family receives equal weight. Normalize
weights to sum to the training-row count. A cell containing `n` rows among `g`
lineages in its family has unnormalized row weight `1 / (n * g)`.

Pass the returned weights to the estimator's `sample_weight` fit argument.
Disable estimator `class_weight` for this arm to avoid applying family
balancing twice. Keep the entire lineage together in upstream grouped splits,
including components with mixed recorded labels. Fit preprocessing on training
rows only; the current sensitivity leaves preprocessing unweighted and weights
only the classifier objective. For random forests this does not change the
bootstrap sampling distribution; it weights the estimator fitting objective.

Compare against an unmodified reference on the same fixed folds. Report
per-family metrics, macro-F1, balanced accuracy, exact sample membership, weight
sums and effective weight sample size. If evaluation also uses weights, label
those metrics separately from ordinary sample-weighted scores. Weighting does
not establish independent lineage or reliable ground truth.

The attached CCNCPS 2026 paper motivates sensitivity to dominant families. This
implementation is a related weighting extension, **not** the paper's hard
family-cap experiment or a reproduction of its fused permission/AV result.
The original and later paper populations differ from current AV-only data.
Repeated selection on development folds cannot establish generalization gains.
Keep baseline artifacts unchanged and require a separate independent evaluation
before promotion.
