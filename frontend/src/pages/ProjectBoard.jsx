import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core'
import { DotsSixVertical } from '@phosphor-icons/react'
import { Page } from '../components/Page'
import { createProject, listProjects, setStage } from '../api/projects'
import { errorMessage } from '../api/client'
import { parseDate } from '../lib/format'

const STAGES = [
  ['idea', 'Idea'], ['scripting', 'Scripting'], ['recording', 'Recording'], ['editing', 'Editing'],
  ['review', 'Review'], ['scheduled', 'Scheduled'], ['published', 'Published'],
]
const LABEL = Object.fromEntries(STAGES)

function CardBody({ project, handle }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-zinc-200 bg-white p-3 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
      {handle}
      <div className="min-w-0">
        <Link to={`/projects/${project.id}`} className="block text-sm font-medium leading-snug hover:text-orange-600 dark:hover:text-orange-400">
          {project.title}
        </Link>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          Updated {parseDate(project.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </p>
      </div>
    </div>
  )
}

function Card({ project }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: project.id, data: { project } })
  const handle = (
    <button
      {...listeners}
      {...attributes}
      aria-label={`Move ${project.title}. Currently in ${LABEL[project.stage]}.`}
      className="mt-0.5 -ml-1 shrink-0 cursor-grab touch-none rounded text-zinc-400 hover:text-zinc-700 focus-visible:outline-2 focus-visible:outline-orange-500 active:cursor-grabbing dark:hover:text-zinc-200"
    >
      <DotsSixVertical size={18} weight="bold" />
    </button>
  )
  return (
    <li ref={setNodeRef} className={isDragging ? 'opacity-40' : ''}>
      <CardBody project={project} handle={handle} />
    </li>
  )
}

function Column({ stage, label, projects }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  return (
    <section
      ref={setNodeRef}
      aria-label={`${label}, ${projects.length} projects`}
      className={`flex w-60 shrink-0 flex-col rounded-lg p-2 transition-colors ${isOver ? 'bg-orange-500/10 ring-1 ring-orange-500/50' : 'bg-zinc-100 dark:bg-zinc-900/60'}`}
    >
      <h2 className="flex items-center justify-between px-1 pt-1 pb-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
        <span className="tabular-nums">{projects.length}</span>
      </h2>
      <ul className="flex min-h-24 flex-1 flex-col gap-2">
        {projects.map((p) => <Card key={p.id} project={p} />)}
      </ul>
    </section>
  )
}

export default function ProjectBoard() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState(null)
  const [title, setTitle] = useState('')
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(null)
  // distance: a click on the title link still navigates; keyboard: space to lift, arrows to move, space to drop
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor))

  useEffect(() => {
    listProjects().then(setProjects).catch((e) => setError(errorMessage(e, 'Could not load projects.')))
  }, [])

  const create = async (e) => {
    e.preventDefault()
    try {
      const p = await createProject({ title })
      navigate(`/projects/${p.id}`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const drop = async ({ active, over }) => {
    setDragging(null)
    const project = active.data.current.project
    if (!over || over.id === project.stage) return
    const before = projects
    setProjects((list) => list.map((p) => (p.id === project.id ? { ...p, stage: over.id } : p))) // optimistic
    try {
      const updated = await setStage(project.id, over.id)
      setProjects((list) => list.map((p) => (p.id === updated.id ? updated : p)))
    } catch (err) {
      setProjects(before)
      setError(errorMessage(err, 'Could not move the project.'))
    }
  }

  return (
    <Page title="Projects" description="Track each piece of content from idea to published. Drag a card to change its stage.">
      <form onSubmit={create} className="flex max-w-xl flex-col gap-3 sm:flex-row sm:items-end">
        <label className="grid flex-1 gap-2 text-sm font-medium">
          New project
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Why cutting coffee won't make you rich"
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm placeholder:text-zinc-500 focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:placeholder:text-zinc-400"
          />
        </label>
        <button className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98]">
          Create
        </button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-8 -mx-4 overflow-x-auto px-4 pb-4 md:-mx-10 md:px-10">
        {projects === null ? (
          <div className="flex gap-3">
            {STAGES.slice(0, 4).map(([s]) => <div key={s} className="h-48 w-60 shrink-0 rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />)}
          </div>
        ) : (
          <DndContext sensors={sensors} onDragStart={({ active }) => setDragging(active.data.current.project)} onDragEnd={drop} onDragCancel={() => setDragging(null)}>
            <div className="flex gap-3">
              {STAGES.map(([stage, label]) => (
                <Column key={stage} stage={stage} label={label} projects={projects.filter((p) => p.stage === stage)} />
              ))}
            </div>
            <DragOverlay dropAnimation={null}>
              {dragging && <div className="w-56 rotate-2"><CardBody project={dragging} /></div>}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </Page>
  )
}
