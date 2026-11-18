# Phase 3 — conversational language audit

Production voice is `female` (`sid=0`). Calls made against the
existing Groq integration; no audio, no human listening claimed.

| lang | gender | code-switch | repetition | script | length | verdict |
|---|---|---|---|---|---|---|
| hi | masculine (want feminine) | kept | varied | ok | ok | FAIL |
| mr | unmarked (want feminine) | kept | varied | ok | ok | PASS (automated) |
| pa | masculine (want feminine) | kept | varied | ok | ok | FAIL |

## Replies (for human review)

### hi
- **cap** · «नमस्ते, क्या आप मेरी मदद कर सकते हैं?» → «नमस्ते! ज़रूर, मैं आपकी कैसे सहायता कर सकता हूँ?» (447 ms)
- **mix** · «मेरा OTP कहाँ आएगा?» → «आपका OTP आपके पंजीकृत मोबाइल पर भेजा जाएगा। क्या आप अपना मोबाइल नंबर पुष्टि कर सकते हैं?» (465 ms)
- **ask** · «मेरा order कब आएगा?» → «कृपया अपना ऑर्डर नंबर बताइए, ताकि मैं ट्रैकिंग स्थिति देख सकूँ।» (448 ms)

### mr
- **cap** · «नमस्कार, तुम्ही मला मदत करू शकता का?» → «नमस्कार! कशात मदत हवी आहे?» (395 ms)
- **mix** · «माझा OTP कुठे येईल?» → «आपला OTP लवकरच आपल्या नोंदणीकृत मोबाईल नंबरवर येईल. काही मिनिटे थांबून बघा, जर आला नाही तर आम्हाला कळवा.» (510 ms)
- **ask** · «माझी order कधी येईल?» → «माफ करा, तुमचा ऑर्डर नंबर मला माहित नाही. कृपया ऑर्डर नंबर द्या, मग मी तपासून सांगतो.» (302 ms)

### pa
- **cap** · «ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਤੁਸੀਂ ਮੇਰੀ ਮਦਦ ਕਰ ਸਕਦੇ ਹੋ?» → «ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਬਿਲਕੁਲ, ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?» (458 ms)
- **mix** · «ਮੇਰਾ OTP ਕਿੱਥੇ ਆਵੇਗਾ?» → «OTP ਤੁਹਾਡੇ ਰਜਿਸਟਰ ਕੀਤੇ ਮੋਬਾਈਲ ਨੰਬਰ ’ਤੇ ਜਾਂ ਈ‑ਮੇਲ ’ਤੇ ਭੇਜਿਆ ਜਾਵੇਗਾ। ਕੀ ਤੁਸੀਂ ਆਪਣਾ ਨੰਬਰ ਜਾਂ ਈ‑ਮੇਲ ਪੁਸ਼ਟੀ ਕਰ ਸਕਦੇ ਹੋ?» (419 ms)
- **ask** · «ਮੇਰਾ order ਕਦੋਂ ਆਵੇਗਾ?» → «ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਨੰਬਰ ਦੱਸੋ, ਤਾਂ ਜੋ ਮੈਂ ਡਿਲਿਵਰੀ ਦੀ ਸਥਿਤੀ ਚੈੱਕ ਕਰ ਸਕਾਂ।» (719 ms)
