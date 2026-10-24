import { ArrowLeft, Gauge, SearchX } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="page">
      <section className="not-found">
        <div className="not-found__code">404</div>
        <SearchX size={34} aria-hidden="true" />
        <h1>页面不存在</h1>
        <p>该地址没有对应的测试视图。请从运行记录或总览重新进入。</p>
        <div className="not-found__actions">
          <Link className="button button--primary" to="/">
            <Gauge size={15} /> 返回总览
          </Link>
          <Link className="button button--ghost" to="/runs">
            <ArrowLeft size={15} /> 运行记录
          </Link>
        </div>
      </section>
    </div>
  );
}
