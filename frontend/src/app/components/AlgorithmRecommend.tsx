'use client';

interface Algorithm {
  name_cn: string;
  name_en: string;
  relevance_score: number;
  description: string;
  applicable_scenarios: string[];
  mathematical_model: string;
  advantages: string[];
  limitations: string[];
  subtypes?: Record<string, string>;
}

interface AlgorithmRecommendProps {
  algorithms: Algorithm[];
}

export default function AlgorithmRecommend({ algorithms }: AlgorithmRecommendProps) {
  if (!algorithms || algorithms.length === 0) return null;

  return (
    <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem] mb-4">
      <div className="flex justify-between items-center mb-[0.8rem]">
        <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">🔍 算法库推荐</span>
        <span className="text-[0.875rem] text-[#94A3B8]">基于问题特征自动检索</span>
      </div>
      <div className="flex flex-col gap-[0.6rem]">
        {algorithms.map((algo, idx) => (
          <div key={algo.name_en} className="bg-black/20 border border-[#334155] rounded-[10px] overflow-hidden">
            <div className="flex items-center gap-2 py-[0.6rem] px-[0.8rem] bg-[rgba(45,212,191,0.15)] border-b border-[#334155]">
              <span className="text-[0.875rem] text-[#3498db] font-bold bg-[rgba(45,212,191,0.15)] py-[0.1rem] px-[0.4rem] rounded-[4px]">#{idx + 1}</span>
              <span className="text-[0.9375rem] text-[#F8FAFC] font-semibold">{algo.name_cn}</span>
              <span className="text-[0.875rem] text-[#94A3B8] italic">{algo.name_en}</span>
              <span className="ml-auto text-[0.72rem] text-[#2ecc71] font-semibold">相关度 {algo.relevance_score}</span>
            </div>
            <div className="py-[0.7rem] px-[0.8rem]">
              <div className="flex gap-2 mb-[0.4rem] items-start">
                <span className="text-[0.875rem] text-[#94A3B8] font-semibold min-w-[60px] shrink-0">描述</span>
                <span className="text-[0.82rem] text-[#94A3B8] leading-[1.5]">{algo.description}</span>
              </div>
              <div className="flex gap-2 mb-[0.4rem] items-start">
                <span className="text-[0.875rem] text-[#94A3B8] font-semibold min-w-[60px] shrink-0">适用场景</span>
                <span className="text-[0.82rem] text-[#94A3B8] leading-[1.5]">{algo.applicable_scenarios.slice(0, 3).join(' · ')}</span>
              </div>
              <div className="flex gap-2 mb-[0.4rem] items-start">
                <span className="text-[0.875rem] text-[#94A3B8] font-semibold min-w-[60px] shrink-0">数学模型</span>
                <span className="text-[0.875rem] text-[#CBD5E1] font-mono leading-[1.5]">{algo.mathematical_model}</span>
              </div>
              {algo.subtypes && Object.keys(algo.subtypes).length > 0 && (
                <div className="flex gap-2 mb-[0.4rem] items-start">
                  <span className="text-[0.875rem] text-[#94A3B8] font-semibold min-w-[60px] shrink-0">具体方法</span>
                  <div className="flex flex-wrap gap-[0.3rem]">
                    {Object.keys(algo.subtypes).map(st => (
                      <span key={st} className="text-[0.72rem] py-[0.15rem] px-2 bg-[rgba(155,89,182,0.15)] rounded-[10px] text-[#bb8fce]">{st}</span>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex gap-4 mt-[0.4rem] flex-wrap">
                {algo.advantages.length > 0 && (
                  <div className="text-[0.78rem] text-[#94A3B8]">
                    <span className="text-[#2ecc71] font-semibold mr-[0.3rem]">优点</span>
                    {algo.advantages.join(' · ')}
                  </div>
                )}
                {algo.limitations.length > 0 && (
                  <div className="text-[0.78rem] text-[#94A3B8]">
                    <span className="text-[#e74c3c] font-semibold mr-[0.3rem]">局限</span>
                    {algo.limitations.join(' · ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
