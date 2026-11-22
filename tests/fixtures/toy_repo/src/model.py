"""SparseMix model: top-k routed mixture of small MLP experts."""

N_EXPERTS = 8
TOP_K = 2


class SparseMix:
    def __init__(self, in_dim: int, hidden_dim: int = 64, n_experts: int = N_EXPERTS, top_k: int = TOP_K):
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        self.n_experts = n_experts
        self.top_k = top_k

    def route(self, x):
        """Return the indices of the top_k experts for each row of x."""
        raise NotImplementedError
