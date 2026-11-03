/** Shown only when the backend reports that every route has No Travel miles. */
export function GlobalWarning() {
  return (
    <div className="banner banner-danger" role="alert">
      <p className="banner-title">No safe route for this trip</p>
      <p>
        Every route has No Travel miles at the planned time. The top route is the best available, but it is not safe.
        Consider a different departure time.
      </p>
    </div>
  )
}

/** The backend's note when fewer than three distinct routes exist. */
export function RouteNotice({ notice }: { notice: string }) {
  return (
    <div className="banner banner-info" role="note">
      <p>{notice}</p>
    </div>
  )
}
