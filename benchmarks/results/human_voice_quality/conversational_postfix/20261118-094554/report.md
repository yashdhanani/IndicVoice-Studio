# Phase 3 — conversational language audit

Production voice is `female` (`sid=0`). Calls made against the
existing Groq integration; no audio, no human listening claimed.

| lang | gender | code-switch | repetition | script | length | verdict |
|---|---|---|---|---|---|---|
| hi | unmarked (want feminine) | kept | varied | ok | ok | PASS (automated) |
| mr | unmarked (want feminine) | kept | varied | ok | ok | PASS (automated) |
| pa | feminine (want feminine) | kept | varied | ok | ok | PASS (automated) |

## Replies (for human review)

### hi
- **cap** · «नमस्ते, क्या आप मेरी मदद कर सकते हैं?» → «नमस्ते! ज़रूर, बताइए आपको किस विषय में सहायता चाहिए?» (312 ms)
- **mix** · «मेरा OTP कहाँ आएगा?» → «आपका OTP आपके मोबाइल पर SMS के रूप में आएगा। क्या आपका नंबर सही है?» (434 ms)
- **ask** · «मेरा order कब आएगा?» → «कृपया अपना ऑर्डर नंबर बताइए, ताकि मैं ट्रैकिंग स्थिति देख सकूँ।» (458 ms)

### mr
- **cap** · «नमस्कार, तुम्ही मला मदत करू शकता का?» → «नमस्कार! नक्कीच, मी मदत करू शकते. कृपया सांगा, तुम्हाला कोणत्या विषयावर मदत हवी आहे?» (281 ms)
- **mix** · «माझा OTP कुठे येईल?» → «तुमच्या फोनवर OTP येईल, कृपया तुमचा मोबाइल नंबर सांगा.» (594 ms)
- **ask** · «माझी order कधी येईल?» → «कृपया तुमचा ऑर्डर क्रमांक सांगाल का? त्यामुळे मला तपासून सांगता येईल.» (455 ms)

### pa
- **cap** · «ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਤੁਸੀਂ ਮੇਰੀ ਮਦਦ ਕਰ ਸਕਦੇ ਹੋ?» → «ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਬਿਲਕੁਲ, ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦੀ ਹਾਂ?» (466 ms)
- **mix** · «ਮੇਰਾ OTP ਕਿੱਥੇ ਆਵੇਗਾ?» → «ਤੁਹਾਡਾ OTP ਤੁਹਾਡੇ ਰਜਿਸਟਰਡ ਮੋਬਾਈਲ ਨੰਬਰ 'ਤੇ ਆਵੇਗਾ। ਕੀ ਤੁਸੀਂ ਆਪਣਾ ਨੰਬਰ ਪੁਸ਼ਟੀ ਕਰ ਸਕਦੇ ਹੋ?» (431 ms)
- **ask** · «ਮੇਰਾ order ਕਦੋਂ ਆਵੇਗਾ?» → «ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਨੰਬਰ ਦੱਸੋ, ਤਾਂ ਕਿ ਮੈਂ ਡਿਲਿਵਰੀ ਦੀ ਤਰੀਕ ਚੈੱਕ ਕਰ ਸਕਾਂ।» (468 ms)
