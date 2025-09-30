import { PublicKey } from '@solana/web3.js';

// Solend program IDs and addresses
export const SOLEND_RESERVES = {
    LENDING_MARKET: '4UpD2fh7xH3VP9QQaXtsS1YY3bxzWhtfpks7FatyKvdY',
    SOL_RESERVE: 'BgxfHJDzm44T7XG68MYKx7YisTjZu73tVovyZSjJMpmw',
    USDC_RESERVE: 'BgxfHJDzm44T7XG68MYKx7YisTjZu73tVovyZSjJMpmw',
    USDT_RESERVE: 'BTsbZDV7aCMRJ3VNy9ygV4Q2UeEo9GpR8D6VV4pgJRZB',
};

// Common token addresses on Solana mainnet
export const TOKEN_MINTS = {
    SOL: 'So11111111111111111111111111111111111111112',
    USDC: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    USDT: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    BTC: '9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E',
    ETH: '2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk',
    RAY: '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R',
};

// Pool addresses for common token pairs
export const POOL_ADDRESSES = {
    SOL_USDC: '58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2',
    SOL_USDT: '7XawhbbxtsRcQA8KTkHT9f9nc6d69UwqCDh6U5EEbEmX',
    ETH_USDC: '5qoTq3qC4U7vFxo3iCzbXcaD1UJmyAJWd8Q6FkVfoSLx',
    RAY_USDC: 'APDFRM3HMr8CAGXwKHiu2f5ePSpaiEJhaeewhQ4JdLjs',
};