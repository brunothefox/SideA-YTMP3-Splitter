# Accuracy evaluation

No real-world accuracy score is claimed. Measure with recordings you own or are permitted to use; never commit private audio or transcripts.

Label words with start/end times and label passages requiring removal. Run the app with each language, quality and device option, save the predicted review report/transcript, and compare using `evaluate.py`. It reports word error rate, edit precision/recall, missed passages and false alarms (interval IoU threshold 0.3).

Keep a held-out set spanning singing/speech, genres, accents/languages, slang, overlapping vocals, clean songs, and ambiguous themes. Measure elapsed time, hardware, model and seconds processed. Re-evaluate after model, dictionary, quantization or separation changes. Report results by group, not just a combined number. Human review remains necessary; these metrics are not Roblox moderation acceptance rates.
