const test = require("node:test");
const assert = require("node:assert/strict");
const { createAuthMiddleware, parseApiKeys } = require("../src/api/auth");

test("parseApiKeys maps tokens to user IDs", () => {
    const config = {
        get: () => "alpha:42,beta"
    };
    const map = parseApiKeys(config);

    assert.equal(map.get("alpha"), 42);
    assert.equal(map.get("beta"), 2);
});

test("createAuthMiddleware rejects missing auth header", () => {
    const config = {
        get: () => "alpha:42"
    };
    const middleware = createAuthMiddleware(config);

    const req = { headers: {} };
    const res = {
        statusCode: null,
        body: null,
        status(code) {
            this.statusCode = code;
            return this;
        },
        json(payload) {
            this.body = payload;
            return this;
        }
    };
    let nextCalled = false;

    middleware(req, res, () => {
        nextCalled = true;
    });

    assert.equal(nextCalled, false);
    assert.equal(res.statusCode, 401);
    assert.equal(res.body.error, "Unauthorized");
});

test("createAuthMiddleware rejects invalid token", () => {
    const config = {
        get: () => "alpha:42"
    };
    const middleware = createAuthMiddleware(config);

    const req = { headers: { authorization: "Bearer nope" } };
    const res = {
        statusCode: null,
        body: null,
        status(code) {
            this.statusCode = code;
            return this;
        },
        json(payload) {
            this.body = payload;
            return this;
        }
    };
    let nextCalled = false;

    middleware(req, res, () => {
        nextCalled = true;
    });

    assert.equal(nextCalled, false);
    assert.equal(res.statusCode, 401);
    assert.equal(res.body.error, "Unauthorized");
});

test("createAuthMiddleware accepts valid token and sets user context", () => {
    const config = {
        get: () => "alpha:42"
    };
    const middleware = createAuthMiddleware(config);

    const req = { headers: { authorization: "Bearer alpha" } };
    const res = {
        statusCode: null,
        body: null,
        status(code) {
            this.statusCode = code;
            return this;
        },
        json(payload) {
            this.body = payload;
            return this;
        }
    };
    let nextCalled = false;

    middleware(req, res, () => {
        nextCalled = true;
    });

    assert.equal(nextCalled, true);
    assert.equal(req.userId, 42);
    assert.equal(req.apiKey, "alpha");
});
