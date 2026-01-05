function makeConfig(values) {
    return {
        get: (key) => values[key]
    };
}

module.exports = {
    makeConfig
};
