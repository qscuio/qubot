const { EventEmitter } = require("node:events");
const { Readable } = require("node:stream");

function callExpress(app, { method, url, headers, body }) {
    return new Promise((resolve) => {
        const req = new Readable({
            read() {
                if (body) {
                    this.push(body);
                }
                this.push(null);
            }
        });

        req.method = method;
        req.url = url;
        req.headers = headers || {};
        if (body && !req.headers["content-length"]) {
            req.headers["content-length"] = String(Buffer.byteLength(body));
        }

        const res = new EventEmitter();
        res.statusCode = 200;
        res.headers = {};
        res.setHeader = (name, value) => {
            res.headers[String(name).toLowerCase()] = value;
        };
        res.header = res.setHeader;
        res.getHeader = (name) => res.headers[String(name).toLowerCase()];
        res.status = (code) => {
            res.statusCode = code;
            return res;
        };
        res.json = (payload) => {
            res.body = payload;
            res.emit("finish");
            resolve(res);
            return res;
        };
        res.send = (payload) => {
            res.body = payload;
            res.emit("finish");
            resolve(res);
            return res;
        };
        res.end = (payload) => {
            if (payload !== undefined) {
                res.body = payload;
            }
            res.emit("finish");
            resolve(res);
        };
        res.write = () => {};
        res.writeHead = (code, headers) => {
            res.statusCode = code;
            if (headers) {
                for (const [key, value] of Object.entries(headers)) {
                    res.setHeader(key, value);
                }
            }
        };

        app.handle(req, res);
    });
}

module.exports = {
    callExpress
};
