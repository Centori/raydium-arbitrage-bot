import { Token } from '../../models/TokenPair';

export abstract class ExchangeService {
  abstract getName(): string;
  abstract getPrice(tokenA: Token, tokenB: Token): Promise<number>;
}