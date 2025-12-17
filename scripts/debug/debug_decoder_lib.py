import googlenewsdecoder

url = "https://news.google.com/rss/articles/CBMikwFBVV95cUxPYlZLN2dPQkFvMlhFQjE1d09VRk5VRkNlY0lXaXZEbFJTc2FJNmZMRHpoSlVzSGVEeGRsMXBTd0hDcHZhaUhYTUswbHJYVVpiSlktbVVobWxsRWJ5aVluOV9TQ3hjYjdUQUZ1djg1SFdoTXI3aDEyemE5cWU2U3cxQ1N4LWZKY3BlMTJpSUx4LV9ELXc?oc=5"

try:
    result = googlenewsdecoder.new_decoderv1(url)
    print(f"Result: {result}")
    if result.get('status'):
        print(f"Decoded URL: {result.get('decoded_url')}")
except Exception as e:
    print(f"Error decoding: {e}")
