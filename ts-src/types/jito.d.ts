import { Transaction, PublicKey, Keypair } from "@solana/web3.js";

declare module 'jito-ts' {
  export namespace bundle {
    interface Bundle {
      transactions: Transaction[];
      hash: string;
    }

    interface BundleResult {
      success: boolean;
      error?: string;
      bundleHash?: string;
    }
  }

  export namespace searcher {
    interface SearcherClient {
      connect(): Promise<void>;
      disconnect(): Promise<void>;
      sendBundle(bundle: bundle.Bundle): Promise<bundle.BundleResult>;
      getNextLeader(): Promise<PublicKey>;
    }

    interface SearcherClientConfig {
      authKeypair: Keypair;
      endpoint: string;
    }
  }

  export namespace blockEngine {
    interface BlockEngineClient {
      submitBundle(bundle: bundle.Bundle): Promise<bundle.BundleResult>;
      getNextScheduledLeader(): Promise<PublicKey>;
    }
  }
}