-- Pearson correlation must lie within [-1, 1] (small float tolerance).
select corr_key, correlation
from {{ ref('fct_rolling_correlations') }}
where correlation < -1.0001
   or correlation >  1.0001
