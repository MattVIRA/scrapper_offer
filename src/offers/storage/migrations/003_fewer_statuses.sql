-- Schema version 3: only three statuses are left (T3.12).
-- « À voir » and « Intéressant » become no status; « Réponse » meant the
-- user had applied.
UPDATE tracking SET status = NULL WHERE status IN ('to_review', 'interesting');
UPDATE tracking SET status = 'applied' WHERE status = 'answered';
