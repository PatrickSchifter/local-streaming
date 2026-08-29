import asyncio, base64, hashlib, json, sys, websockets

PW="T1iKpEgZBdQHo3yy"; URL="ws://127.0.0.1:4455"

async def main():
    async with websockets.connect(URL, max_size=64*1024*1024) as ws:
        hello=json.loads(await ws.recv())
        d=hello["d"]; ident={"rpcVersion":1}
        if "authentication" in d:
            a=d["authentication"]
            sec=base64.b64encode(hashlib.sha256((PW+a["salt"]).encode()).digest()).decode()
            ident["authentication"]=base64.b64encode(
                hashlib.sha256((sec+a["challenge"]).encode()).digest()).decode()
        await ws.send(json.dumps({"op":1,"d":ident}))
        r=json.loads(await ws.recv())
        if r["op"]!=2: print("falha na autenticacao:",r); return
        print("conectado ao obs-websocket")

        async def req(t,data=None,rid="1"):
            await ws.send(json.dumps({"op":6,"d":{"requestType":t,"requestId":rid,
                                                 "requestData":data or {}}}))
            while True:
                m=json.loads(await ws.recv())
                if m["op"]==7 and m["d"]["requestId"]==rid: return m["d"]

        SRC="Jogo (Windows via SRT)"
        st=await req("GetMediaInputStatus",{"inputName":SRC})
        print("media status:", json.dumps(st.get("responseData",{}),ensure_ascii=False))
        print("       status:", st["requestStatus"])

        shot=await req("GetSourceScreenshot",
                       {"sourceName":SRC,"imageFormat":"png","imageWidth":1280},"2")
        if shot["requestStatus"]["result"]:
            b64=shot["responseData"]["imageData"].split(",",1)[1]
            open(sys.argv[1],"wb").write(base64.b64decode(b64))
            print("screenshot salvo:", sys.argv[1])
        else:
            print("screenshot falhou:", shot["requestStatus"])

asyncio.run(main())
